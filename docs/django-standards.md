# Django Framework Standards

> Auto-loaded by Level 2 Standards System
> Layered on top of the language-level Python standards (`docs/02-backend-standards.md`) — this file covers Django-specific idioms only.

---

## 1. ORM Query Efficiency

### Rule 1.1: Always Use `select_related`/`prefetch_related` to Avoid N+1 Queries
- `select_related` for forward foreign keys / one-to-one (SQL JOIN), `prefetch_related` for reverse FKs / many-to-many (separate query, joined in Python)

```python
# BAD - N+1 queries: one for orders, one per order for its customer
orders = Order.objects.all()
for order in orders:
    print(order.customer.name)  # separate query every iteration

# GOOD - single JOIN query
orders = Order.objects.select_related('customer').all()
for order in orders:
    print(order.customer.name)  # no extra query

# GOOD - reverse FK / M2M, one extra query total (not per row)
customers = Customer.objects.prefetch_related('orders').all()
```

### Rule 1.2: Use `only()`/`defer()` When You Don't Need the Full Row
- Fetching every column of a wide table when only 2-3 fields are used wastes bandwidth and memory

```python
# BAD - fetches every column including large text/blob fields
users = User.objects.all()
emails = [u.email for u in users]

# GOOD - fetches only what's used
emails = User.objects.only('email').values_list('email', flat=True)
```

### Rule 1.3: Never Call `.count()` After Already Evaluating the Queryset
- Each queryset method call that isn't chained before evaluation re-hits the database

```python
# BAD - two separate queries
users = User.objects.filter(is_active=True)
total = users.count()
first_five = users[:5]

# GOOD - one queryset, evaluated once, sliced/counted from the cached result
users = list(User.objects.filter(is_active=True))
total = len(users)
first_five = users[:5]
```

---

## 2. Django REST Framework

### Rule 2.1: Use `ModelSerializer` for Standard CRUD, Explicit `Serializer` for Custom Shapes
- Don't hand-write field-by-field serializers for a straight model-to-JSON mapping — `ModelSerializer` generates it
- Switch to an explicit `Serializer` only when the output shape diverges from the model

```python
# GOOD - standard CRUD, let ModelSerializer generate fields
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'created_at']
        read_only_fields = ['id', 'created_at']

# GOOD - custom aggregated shape, explicit serializer
class UserStatsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    order_count = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
```

### Rule 2.2: Use `ViewSet` + Router for Standard Resource Endpoints, Function Views Only for One-Offs
- A `ModelViewSet` gives list/create/retrieve/update/destroy for free, registered with one router line

```python
# GOOD - one class covers the full CRUD surface
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

# urls.py
router = DefaultRouter()
router.register('users', UserViewSet)
```

### Rule 2.3: Put Business Logic in the Serializer's `create`/`update` or a Service Layer, Never in the View
- Views should orchestrate (parse request, call serializer/service, return response) — not contain business rules

```python
# BAD - business logic embedded in the view
class UserViewSet(viewsets.ModelViewSet):
    def create(self, request):
        if User.objects.filter(email=request.data['email']).exists():
            return Response({"error": "duplicate"}, status=409)
        user = User.objects.create(**request.data)
        send_welcome_email(user)
        return Response(UserSerializer(user).data, status=201)

# GOOD - view delegates, serializer/service owns the rule
class UserSerializer(serializers.ModelSerializer):
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("duplicate email")
        return value

    def create(self, validated_data):
        user = User.objects.create(**validated_data)
        send_welcome_email(user)
        return user
```

---

## 3. Settings Management

### Rule 3.1: Split Settings by Environment, Source Secrets from Environment Variables
- Never commit `SECRET_KEY`, database passwords, or API keys directly in `settings.py`

```python
# BAD
SECRET_KEY = 'django-insecure-abc123'
DATABASES = {'default': {'PASSWORD': 'hunter2'}}

# GOOD - use django-environ or os.environ, split base/dev/prod settings
# settings/base.py
env = environ.Env()
SECRET_KEY = env('SECRET_KEY')
DATABASES = {'default': env.db('DATABASE_URL')}

# settings/prod.py
from .base import *
DEBUG = False
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')
```

---

## 4. Migrations

### Rule 4.1: Never Edit an Already-Applied Migration File
- Once a migration has run anywhere (staging, another developer's machine), editing it desyncs migration history
- Create a new migration to fix a mistake instead

```bash
# BAD - editing 0003_add_phone_field.py after it's been applied elsewhere

# GOOD - new migration to correct it
python manage.py makemigrations myapp --name fix_phone_field_length
```

### Rule 4.2: Review Auto-Generated Migrations Before Committing
- `makemigrations` can produce destructive operations (e.g., dropping a column) that aren't obvious from the model diff alone — always read the generated migration file

---

## 5. Views

### Rule 5.1: Prefer Class-Based Views for Standard Patterns, Function Views for Simple One-Offs
- `ListView`, `DetailView`, `CreateView` etc. eliminate boilerplate for standard CRUD pages
- Don't force a CBV for a single-purpose view with no reusable structure — a function view is clearer there

```python
# GOOD - CBV for standard list/detail pattern
class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).select_related('customer')

# GOOD - function view for a one-off action with no reusable structure
@login_required
def resend_confirmation_email(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    send_confirmation_email(order)
    return redirect('order-detail', order_id=order.id)
```

---

## 6. Signals

### Rule 6.1: Use Signals Sparingly - Prefer Explicit Calls in Service/View Code
- Signals decouple cause and effect to the point where a reader can't trace what happens after `.save()` without grepping the whole codebase
- Reserve signals for cross-cutting concerns that genuinely can't have an explicit call site (e.g., third-party app integration)

```python
# RISKY - side effect is invisible at the call site
@receiver(post_save, sender=Order)
def send_order_confirmation(sender, instance, created, **kwargs):
    if created:
        send_confirmation_email(instance)

# CLEARER - explicit, traceable from the call site
class OrderService:
    def create_order(self, **data):
        order = Order.objects.create(**data)
        send_confirmation_email(order)
        return order
```

---

## 7. Testing

### Rule 7.1: Use `TestCase` (Transaction-Wrapped) Over `TransactionTestCase` Unless You're Testing Transaction Behavior Itself
- `TestCase` wraps each test in a transaction and rolls back, much faster than `TransactionTestCase`, which truncates tables

```python
# GOOD - fast, isolated, wrapped in a rolled-back transaction
class OrderServiceTests(TestCase):
    def test_create_order_sends_confirmation_email(self):
        customer = CustomerFactory()
        order = OrderService().create_order(customer=customer, items=[...])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [customer.email])
```

### Rule 7.2: Use Factories (factory_boy) Instead of Hardcoded Fixture Objects
- Factories keep test setup close to the test and avoid fragile shared fixture files

```python
# GOOD
class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker('name')
```

---

## 8. Common LLM Mistakes to Avoid

- Iterating a queryset that accesses a related object per row without `select_related`/`prefetch_related` (N+1 queries)
- Putting business logic directly in DRF views instead of the serializer or a service layer
- Hardcoding `SECRET_KEY` or database credentials in `settings.py` instead of environment variables
- Editing an already-applied migration file instead of creating a new one
- Overusing signals for logic that should be an explicit, traceable function call
- Using `TransactionTestCase` by default instead of the faster transaction-wrapped `TestCase`
- Forcing a class-based view for a single-purpose action that a function view would express more clearly
- Calling `.count()` or slicing a queryset multiple times instead of evaluating it once into a list
