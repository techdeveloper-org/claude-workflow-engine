# 🎯 Automatic Task Breakdown & Status Tracking Policy

**VERSION:** 2.0.0
**CREATED:** 2026-02-16
**UPDATED:** 2026-02-22 — Always-Task Policy (v2.0.0)
**PRIORITY:** CRITICAL - STEP 1 (After Prompt Generation)
**STATUS:** ACTIVE

---

## 📋 POLICY OVERVIEW

**MANDATORY: After Step 0 (Prompt Generation), automatically:**

1. ✅ **ALWAYS create tasks** — complexity nahi dekhna, EVERY coding request pe TaskCreate
2. ✅ **Break down** into phases (when 5+ tasks are generated)
3. ✅ **Minimum 1 task** per request — policy visibility ke liye
4. ✅ **Auto-track** status as Claude works
5. ✅ **Auto-update** progress without manual intervention

**v2.0.0 KEY CHANGE:** Task creation is NO LONGER complexity-based.
Tasks are created on EVERY implementation request regardless of size.
Purpose: User sees that policies are running on every request.

---

## 🚨 EXECUTION ORDER

```
Step 0: Structured Prompt Generated
        ↓
🔴 STEP 1: AUTOMATIC TASK BREAKDOWN (THIS POLICY)
        ↓
    Analyze Complexity
        ↓
    Divide into Phases (if needed)
        ↓
    Break Phases into Tasks
        ↓
    Create All Tasks Automatically
        ↓
    🤖 Auto-Tracker Daemon Starts
        ↓
    As Claude Works → Auto-Update Status
        ↓
Step 2: Context Check
Step 3: Model Selection
... (rest of pipeline)
```

---

## 🎯 BREAKDOWN ALGORITHM

### **Step 1.1: Analyze Complexity**

```python
def analyze_complexity(structured_prompt: Dict) -> Dict:
    """
    Analyze task complexity to determine breakdown strategy
    """
    complexity_score = 0

    # Factor 1: Number of files to create/modify
    files_count = (
        len(structured_prompt.get('expected_output', {}).get('files_created', [])) +
        len(structured_prompt.get('expected_output', {}).get('files_modified', []))
    )
    complexity_score += min(files_count, 10)

    # Factor 2: Number of operations
    operations_count = len(structured_prompt.get('analysis', {}).get('operations', []))
    complexity_score += operations_count * 2

    # Factor 3: Number of entities involved
    entities_count = len(structured_prompt.get('analysis', {}).get('entities', []))
    complexity_score += entities_count * 3

    # Factor 4: Dependencies
    dependencies_count = len(structured_prompt.get('conditions', {}).get('pre_conditions', []))
    complexity_score += dependencies_count

    # Factor 5: Task type complexity weights
    task_type = structured_prompt.get('task_type', 'General Task')
    complexity_weights = {
        'API Creation': 5,
        'Authentication': 8,
        'Authorization': 7,
        'Database Migration': 9,
        'Security Enhancement': 8,
        'Bug Fix': 2,
        'Refactoring': 6
    }
    complexity_score += complexity_weights.get(task_type, 3)

    return {
        'score': complexity_score,
        'level': get_complexity_level(complexity_score),
        'needs_phases': complexity_score >= 10,
        'needs_tasks': complexity_score >= 5,
        'estimated_tasks': max(files_count, 3)
    }

def get_complexity_level(score: int) -> str:
    if score < 5:
        return 'SIMPLE'
    elif score < 10:
        return 'MODERATE'
    elif score < 20:
        return 'COMPLEX'
    else:
        return 'VERY_COMPLEX'
```

**Complexity Decision Matrix (v2.0.0 — Always-Task Policy):**

| Score | Level | Phases? | Tasks? | Strategy |
|-------|-------|---------|--------|----------|
| 0-4 | SIMPLE | No | YES (min 1) | 1 task — always create (v2.0.0 change) |
| 5-9 | MODERATE | No | YES (3-5) | Multiple tasks, no phases |
| 10-19 | COMPLEX | YES | YES (6-12) | 2-3 phases, tasks per phase |
| 20+ | VERY_COMPLEX | YES | YES (12+) | 4+ phases, granular tasks |

NOTE (v2.0.0): Tasks column is ALWAYS YES. Phase trigger: 5+ tasks = use phases.

---

### **Step 1.2: Divide into Phases**

```python
def divide_into_phases(structured_prompt: Dict, complexity: Dict) -> List[Dict]:
    """
    Divide task into logical phases based on task type
    """
    task_type = structured_prompt.get('task_type')

    # Phase templates by task type
    phase_templates = {
        'API Creation': [
            {
                'name': 'Foundation',
                'description': 'Create entities, repositories, basic structure',
                'order': 1,
                'tasks_pattern': ['entity', 'repository']
            },
            {
                'name': 'Business Logic',
                'description': 'Implement service layer with business rules',
                'order': 2,
                'tasks_pattern': ['service', 'service.impl', 'helper']
            },
            {
                'name': 'API Layer',
                'description': 'Create controllers, DTOs, Forms',
                'order': 3,
                'tasks_pattern': ['controller', 'dto', 'form']
            },
            {
                'name': 'Configuration',
                'description': 'Add configurations, validation, testing',
                'order': 4,
                'tasks_pattern': ['config', 'validation', 'test']
            }
        ],

        'Authentication': [
            {
                'name': 'Security Setup',
                'description': 'Configure Spring Security, JWT utilities',
                'order': 1,
                'tasks_pattern': ['security.config', 'jwt.util']
            },
            {
                'name': 'Authentication Flow',
                'description': 'Implement login, token generation',
                'order': 2,
                'tasks_pattern': ['auth.controller', 'auth.service']
            },
            {
                'name': 'Authorization',
                'description': 'Add role-based access control',
                'order': 3,
                'tasks_pattern': ['roles', 'permissions', 'filters']
            },
            {
                'name': 'Integration',
                'description': 'Integrate with services, test endpoints',
                'order': 4,
                'tasks_pattern': ['integration', 'testing']
            }
        ],

        'Database Migration': [
            {
                'name': 'Backup',
                'description': 'Create backup, verify backup integrity',
                'order': 1,
                'tasks_pattern': ['backup', 'verify']
            },
            {
                'name': 'Schema Changes',
                'description': 'Create migration scripts, update entities',
                'order': 2,
                'tasks_pattern': ['migration.scripts', 'entities']
            },
            {
                'name': 'Data Migration',
                'description': 'Migrate data, validate integrity',
                'order': 3,
                'tasks_pattern': ['data.migration', 'validation']
            },
            {
                'name': 'Rollback Plan',
                'description': 'Create rollback scripts, test rollback',
                'order': 4,
                'tasks_pattern': ['rollback.script', 'rollback.test']
            }
        ]
    }

    # Get template or create generic phases
    template = phase_templates.get(task_type, create_generic_phases(structured_prompt))

    return template


def create_generic_phases(structured_prompt: Dict) -> List[Dict]:
    """Create generic phases for unknown task types"""
    return [
        {
            'name': 'Preparation',
            'description': 'Setup, dependencies, initial structure',
            'order': 1,
            'tasks_pattern': ['setup']
        },
        {
            'name': 'Implementation',
            'description': 'Core functionality implementation',
            'order': 2,
            'tasks_pattern': ['implementation']
        },
        {
            'name': 'Testing & Validation',
            'description': 'Test functionality, validate results',
            'order': 3,
            'tasks_pattern': ['testing']
        }
    ]
```

---

### **Step 1.3: Break Phases into Tasks**

```python
def break_into_tasks(phase: Dict, structured_prompt: Dict) -> List[Dict]:
    """
    Break a phase into granular tasks
    """
    tasks = []
    files_to_create = structured_prompt.get('expected_output', {}).get('files_created', [])
    files_to_modify = structured_prompt.get('expected_output', {}).get('files_modified', [])

    # Match files to this phase based on pattern
    phase_pattern = phase.get('tasks_pattern', [])

    # Create tasks for files to create
    for file_info in files_to_create:
        file_path = file_info.get('path', '')
        file_type = file_info.get('type', '')

        # Check if this file belongs to this phase
        if any(pattern in file_path.lower() or pattern in file_type.lower()
               for pattern in phase_pattern):

            task = {
                'subject': f"Create {file_type}",
                'description': f"Create {file_path}\nPurpose: {file_info.get('purpose', '')}\nExample: {file_info.get('example', '')}",
                'activeForm': f"Creating {file_type}",
                'type': 'file_creation',
                'file_path': file_path,
                'file_type': file_type,
                'phase': phase.get('name'),
                'order': len(tasks) + 1,
                'estimated_steps': 3,  # Read example, adapt, write
                'dependencies': []
            }
            tasks.append(task)

    # Create tasks for files to modify
    for file_info in files_to_modify:
        file_path = file_info.get('path', '')

        if any(pattern in file_path.lower() for pattern in phase_pattern):
            task = {
                'subject': f"Modify {file_path.split('/')[-1]}",
                'description': f"Modify {file_path}\nChanges: {file_info.get('changes', '')}\nReason: {file_info.get('reason', '')}",
                'activeForm': f"Modifying {file_path.split('/')[-1]}",
                'type': 'file_modification',
                'file_path': file_path,
                'phase': phase.get('name'),
                'order': len(tasks) + 1,
                'estimated_steps': 2,  # Read, edit
                'dependencies': []
            }
            tasks.append(task)

    # Add phase-specific tasks
    if phase.get('name') == 'Configuration':
        configs = structured_prompt.get('expected_output', {}).get('configurations', [])
        for config in configs:
            task = {
                'subject': f"Configure {config.get('location', '').split('/')[-1]}",
                'description': f"Update configuration at {config.get('location', '')}\nChanges: {config.get('changes', [])}",
                'activeForm': f"Configuring service",
                'type': 'configuration',
                'phase': phase.get('name'),
                'order': len(tasks) + 1,
                'estimated_steps': 2
            }
            tasks.append(task)

    if phase.get('name') == 'Testing & Validation':
        success_criteria = structured_prompt.get('success_criteria', [])
        for criterion in success_criteria:
            task = {
                'subject': f"Verify: {criterion[:50]}",
                'description': f"Verify that: {criterion}",
                'activeForm': f"Verifying functionality",
                'type': 'verification',
                'phase': phase.get('name'),
                'order': len(tasks) + 1,
                'estimated_steps': 1
            }
            tasks.append(task)

    return tasks
```

---

### **Step 1.4: Create Task Dependencies**

```python
def create_dependencies(all_tasks: List[Dict]) -> List[Dict]:
    """
    Automatically determine task dependencies
    """
    # Rule 1: Entity must be created before Repository
    entities = [t for t in all_tasks if 'entity' in t['file_type'].lower()]
    repositories = [t for t in all_tasks if 'repository' in t['file_type'].lower()]

    for repo_task in repositories:
        for entity_task in entities:
            if not repo_task.get('dependencies'):
                repo_task['dependencies'] = []
            repo_task['dependencies'].append(entity_task['subject'])

    # Rule 2: Repository must exist before Service
    services = [t for t in all_tasks if 'service' in t['file_type'].lower()]

    for service_task in services:
        for repo_task in repositories:
            if not service_task.get('dependencies'):
                service_task['dependencies'] = []
            service_task['dependencies'].append(repo_task['subject'])

    # Rule 3: Service must exist before Controller
    controllers = [t for t in all_tasks if 'controller' in t['file_type'].lower()]

    for controller_task in controllers:
        for service_task in services:
            if not controller_task.get('dependencies'):
                controller_task['dependencies'] = []
            controller_task['dependencies'].append(service_task['subject'])

    # Rule 4: DTOs and Forms before Controller
    dtos = [t for t in all_tasks if 'dto' in t['file_type'].lower()]
    forms = [t for t in all_tasks if 'form' in t['file_type'].lower()]

    for controller_task in controllers:
        for dto_task in dtos + forms:
            if dto_task['subject'] not in controller_task.get('dependencies', []):
                if not controller_task.get('dependencies'):
                    controller_task['dependencies'] = []
                controller_task['dependencies'].append(dto_task['subject'])

    return all_tasks
```

---

## 🤖 AUTOMATIC STATUS TRACKING

### **Auto-Tracker System:**

```python
class AutoTaskTracker:
    """
    Automatically tracks and updates task status based on Claude's actions
    """

    def __init__(self):
        self.active_tasks = {}
        self.monitoring = True

    def monitor_tool_calls(self, tool_name: str, tool_params: Dict, result: Any):
        """
        Monitor every tool call and auto-update task status
        """
        # Detect which task this tool call relates to
        related_task = self.find_related_task(tool_name, tool_params)

        if not related_task:
            return

        # Auto-update based on tool type
        if tool_name == 'Read':
            self.update_task_progress(
                related_task,
                step='Reading example/existing code',
                progress_increment=10
            )

        elif tool_name == 'Write':
            file_path = tool_params.get('file_path')
            if file_path == related_task.get('file_path'):
                self.update_task_progress(
                    related_task,
                    step='Writing file',
                    progress_increment=40,
                    completed_items=[f"Created {file_path.split('/')[-1]}"]
                )

        elif tool_name == 'Edit':
            file_path = tool_params.get('file_path')
            if file_path == related_task.get('file_path'):
                self.update_task_progress(
                    related_task,
                    step='Modifying file',
                    progress_increment=30,
                    completed_items=[f"Modified {file_path.split('/')[-1]}"]
                )

        elif tool_name == 'Bash':
            command = tool_params.get('command', '')

            # Detect compilation
            if 'mvn clean install' in command or 'mvn compile' in command:
                self.update_task_progress(
                    related_task,
                    step='Building project',
                    progress_increment=20
                )

                # If build successful, mark verification tasks as progressing
                if result and 'BUILD SUCCESS' in str(result):
                    self.complete_verification_tasks('Build successful')

            # Detect testing
            if 'mvn test' in command or 'curl' in command:
                self.update_task_progress(
                    related_task,
                    step='Testing functionality',
                    progress_increment=15
                )

    def find_related_task(self, tool_name: str, tool_params: Dict) -> Optional[Dict]:
        """
        Find which task this tool call relates to
        """
        if tool_name in ['Read', 'Write', 'Edit']:
            file_path = tool_params.get('file_path', '')

            # Match file path to task
            for task_id, task in self.active_tasks.items():
                if task.get('file_path') in file_path:
                    return task

        # If no specific match, return current active task
        current_tasks = [t for t in self.active_tasks.values()
                        if t.get('status') == 'in_progress']

        return current_tasks[0] if current_tasks else None

    def update_task_progress(
        self,
        task: Dict,
        step: str,
        progress_increment: int,
        completed_items: List[str] = None
    ):
        """
        Auto-update task progress
        """
        task_id = task.get('id')
        current_progress = task.get('progress', 0)
        new_progress = min(current_progress + progress_increment, 100)

        metadata = {
            'current_step': step,
            'progress': new_progress,
            'last_updated': datetime.now().isoformat()
        }

        if completed_items:
            existing_completed = task.get('completed_items', [])
            metadata['completed_items'] = existing_completed + completed_items

        # Auto-call TaskUpdate
        TaskUpdate(
            taskId=task_id,
            metadata=metadata
        )

        # If progress reaches 100%, auto-complete
        if new_progress >= 100:
            self.auto_complete_task(task_id)

    def auto_complete_task(self, task_id: str):
        """
        Automatically mark task as completed
        """
        TaskUpdate(
            taskId=task_id,
            status='completed',
            metadata={
                'completed_at': datetime.now().isoformat(),
                'progress': 100
            }
        )

        # Check if this was last task in phase
        self.check_phase_completion(task_id)

    def check_phase_completion(self, completed_task_id: str):
        """
        Check if all tasks in a phase are complete
        """
        completed_task = self.active_tasks.get(completed_task_id)
        phase_name = completed_task.get('phase')

        # Get all tasks in this phase
        phase_tasks = [t for t in self.active_tasks.values()
                      if t.get('phase') == phase_name]

        # Check if all complete
        all_complete = all(t.get('status') == 'completed' for t in phase_tasks)

        if all_complete:
            self.on_phase_complete(phase_name)

    def on_phase_complete(self, phase_name: str):
        """
        Handle phase completion
        """
        print(f"✅ PHASE COMPLETE: {phase_name}")

        # Unlock tasks in next phase
        self.unlock_next_phase_tasks(phase_name)

        # Trigger auto-commit for this phase
        trigger_auto_commit(phase_name)

    def unlock_next_phase_tasks(self, completed_phase: str):
        """
        Unlock tasks that were blocked by this phase
        """
        phase_order = {
            'Foundation': 1,
            'Business Logic': 2,
            'API Layer': 3,
            'Configuration': 4
        }

        current_order = phase_order.get(completed_phase, 0)
        next_order = current_order + 1

        # Find next phase tasks
        next_phase = [name for name, order in phase_order.items()
                     if order == next_order]

        if next_phase:
            next_phase_name = next_phase[0]
            print(f"🔓 UNLOCKING: {next_phase_name} phase tasks")

            # Tasks in next phase can now start
            for task in self.active_tasks.values():
                if task.get('phase') == next_phase_name:
                    task['blocked'] = False
```

---

## 📊 STATUS UPDATE TRIGGERS

### **Automatic Updates Triggered By:**

| Tool Call | Auto-Update | Progress |
|-----------|-------------|----------|
| `Read(example_file)` | "Reading example code" | +10% |
| `Read(target_file)` | "Analyzing existing code" | +10% |
| `Write(file)` | "Creating {filename}" | +40% |
| `Edit(file)` | "Modifying {filename}" | +30% |
| `Bash("mvn compile")` | "Compiling code" | +15% |
| `Bash("mvn test")` | "Running tests" | +15% |
| `Bash("curl ...")` | "Testing endpoint" | +10% |
| Build SUCCESS | "Build verified" | +20% |
| Test PASS | "Tests passed" | +20% |

### **Auto-Completion Triggers:**

```python
auto_complete_conditions = {
    'file_creation': {
        'conditions': [
            'Write tool called for file',
            'File exists verification passed'
        ],
        'auto_complete': True
    },

    'file_modification': {
        'conditions': [
            'Edit tool called',
            'Changes applied successfully'
        ],
        'auto_complete': True
    },

    'configuration': {
        'conditions': [
            'Config file updated',
            'Service can read config'
        ],
        'auto_complete': True
    },

    'verification': {
        'conditions': [
            'Test executed',
            'Success criteria met'
        ],
        'auto_complete': True
    }
}
```

---

## 🎯 COMPLETE BREAKDOWN EXAMPLE

### **Input: "Create Product API with CRUD"**

**Structured Prompt Analysis:**
```yaml
task_type: "API Creation"
complexity_score: 18
level: "COMPLEX"
needs_phases: true
estimated_tasks: 12
```

**Phase Breakdown:**
```yaml
phases:
  - name: "Foundation"
    order: 1
    tasks: 3

  - name: "Business Logic"
    order: 2
    tasks: 3

  - name: "API Layer"
    order: 3
    tasks: 4

  - name: "Configuration"
    order: 4
    tasks: 2
```

**Tasks Auto-Created:**
```yaml
# PHASE 1: Foundation
task_1:
  id: "task_001"
  subject: "Create Product Entity"
  description: "Create Product.java with JPA annotations"
  activeForm: "Creating Product Entity"
  phase: "Foundation"
  order: 1
  dependencies: []
  estimated_steps: 3
  auto_tracking: true

task_2:
  id: "task_002"
  subject: "Create Product Repository"
  description: "Create ProductRepository.java extending JpaRepository"
  activeForm: "Creating Product Repository"
  phase: "Foundation"
  order: 2
  dependencies: ["task_001"]  # Auto-detected
  estimated_steps: 2
  auto_tracking: true

task_3:
  id: "task_003"
  subject: "Create DTO and Form classes"
  description: "Create ProductDto.java and ProductForm.java"
  activeForm: "Creating DTO and Form"
  phase: "Foundation"
  order: 3
  dependencies: ["task_001"]  # Auto-detected
  estimated_steps: 3
  auto_tracking: true

# PHASE 2: Business Logic
task_4:
  id: "task_004"
  subject: "Create Product Service Interface"
  description: "Create ProductService.java with CRUD methods"
  activeForm: "Creating Service Interface"
  phase: "Business Logic"
  order: 4
  dependencies: ["task_002"]  # Auto-detected
  estimated_steps: 2
  auto_tracking: true

task_5:
  id: "task_005"
  subject: "Implement Product Service"
  description: "Create ProductServiceImpl.java with business logic"
  activeForm: "Implementing Business Logic"
  phase: "Business Logic"
  order: 5
  dependencies: ["task_004"]  # Auto-detected
  estimated_steps: 5
  auto_tracking: true

task_6:
  id: "task_006"
  subject: "Add Validation Logic"
  description: "Implement validation rules in service"
  activeForm: "Adding Validation"
  phase: "Business Logic"
  order: 6
  dependencies: ["task_005"]  # Auto-detected
  estimated_steps: 2
  auto_tracking: true

# PHASE 3: API Layer
task_7:
  id: "task_007"
  subject: "Create Product Controller"
  description: "Create ProductController.java with REST endpoints"
  activeForm: "Creating Controller"
  phase: "API Layer"
  order: 7
  dependencies: ["task_005", "task_003"]  # Auto-detected
  estimated_steps: 4
  auto_tracking: true

task_8:
  id: "task_008"
  subject: "Implement CREATE endpoint"
  description: "Add POST /api/v1/products endpoint"
  activeForm: "Implementing CREATE"
  phase: "API Layer"
  order: 8
  dependencies: ["task_007"]
  estimated_steps: 2
  auto_tracking: true

task_9:
  id: "task_009"
  subject: "Implement READ endpoints"
  description: "Add GET /api/v1/products and GET /api/v1/products/{id}"
  activeForm: "Implementing READ"
  phase: "API Layer"
  order: 9
  dependencies: ["task_007"]
  estimated_steps: 2
  auto_tracking: true

task_10:
  id: "task_010"
  subject: "Implement UPDATE endpoint"
  description: "Add PUT /api/v1/products/{id} endpoint"
  activeForm: "Implementing UPDATE"
  phase: "API Layer"
  order: 10
  dependencies: ["task_007"]
  estimated_steps: 2
  auto_tracking: true

task_11:
  id: "task_011"
  subject: "Implement DELETE endpoint"
  description: "Add DELETE /api/v1/products/{id} endpoint"
  activeForm: "Implementing DELETE"
  phase: "API Layer"
  order: 11
  dependencies: ["task_007"]
  estimated_steps: 2
  auto_tracking: true

# PHASE 4: Configuration
task_12:
  id: "task_012"
  subject: "Add Service Configuration"
  description: "Update product-service.yml in config server"
  activeForm: "Configuring Service"
  phase: "Configuration"
  order: 12
  dependencies: []
  estimated_steps: 2
  auto_tracking: true

task_13:
  id: "task_013"
  subject: "Verify Build and Tests"
  description: "Run mvn clean install and test all endpoints"
  activeForm: "Verifying Functionality"
  phase: "Configuration"
  order: 13
  dependencies: ["task_012"]
  estimated_steps: 3
  auto_tracking: true
```

**Auto-Tracking in Action:**
```
Claude: Read("user-service/entity/User.java")
    ↓
Auto-Tracker: TaskUpdate(task_001, metadata={
    current_step: "Reading example entity",
    progress: 10
})

Claude: Write("Product.java")
    ↓
Auto-Tracker: TaskUpdate(task_001, metadata={
    current_step: "Creating Product entity",
    progress: 50,
    completed_items: ["Product.java created"]
})

Claude: Bash("mvn compile")
    ↓
Result: "BUILD SUCCESS"
    ↓
Auto-Tracker: TaskUpdate(task_001, metadata={
    current_step: "Build verified",
    progress: 100
})
    ↓
Auto-Tracker: TaskUpdate(task_001, status="completed")
    ↓
Auto-Tracker: Check dependencies → Unlock task_002, task_003
```

---

## 🔧 IMPLEMENTATION SCRIPT

**File:** `~/.claude/memory/task-auto-breakdown.py`

```python
#!/usr/bin/env python3
"""
Automatic Task Breakdown and Tracking
"""

import json
import yaml
from typing import Dict, List
from datetime import datetime
from pathlib import Path


class AutoTaskBreakdown:
    def __init__(self, structured_prompt: Dict):
        self.prompt = structured_prompt
        self.phases = []
        self.tasks = []
        self.complexity = {}

    def execute(self) -> Dict:
        """
        Main execution: Analyze → Break → Create → Track
        """
        print("=" * 80)
        print("🎯 AUTOMATIC TASK BREAKDOWN")
        print("=" * 80)

        # Step 1: Analyze complexity
        self.complexity = self.analyze_complexity()
        print(f"\n📊 Complexity Analysis:")
        print(f"   Score: {self.complexity['score']}")
        print(f"   Level: {self.complexity['level']}")
        print(f"   Needs Phases: {self.complexity['needs_phases']}")
        print(f"   Estimated Tasks: {self.complexity['estimated_tasks']}")

        # Step 2: Divide into phases (if needed)
        if self.complexity['needs_phases']:
            self.phases = self.divide_into_phases()
            print(f"\n📋 Created {len(self.phases)} Phases:")
            for phase in self.phases:
                print(f"   {phase['order']}. {phase['name']}")

        # Step 3: Break into tasks
        self.tasks = self.break_into_tasks()
        print(f"\n✅ Created {len(self.tasks)} Tasks")

        # Step 4: Create dependencies
        self.tasks = self.create_dependencies(self.tasks)

        # Step 5: Generate output
        return self.generate_output()

    def analyze_complexity(self) -> Dict:
        """Analyze task complexity"""
        # Implementation from algorithm above
        pass

    def divide_into_phases(self) -> List[Dict]:
        """Divide into phases"""
        # Implementation from algorithm above
        pass

    def break_into_tasks(self) -> List[Dict]:
        """Break phases into tasks"""
        # Implementation from algorithm above
        pass

    def create_dependencies(self, tasks: List[Dict]) -> List[Dict]:
        """Create task dependencies"""
        # Implementation from algorithm above
        pass

    def generate_output(self) -> Dict:
        """Generate final breakdown"""
        return {
            'complexity': self.complexity,
            'phases': self.phases,
            'tasks': self.tasks,
            'auto_tracking_enabled': True,
            'created_at': datetime.now().isoformat()
        }


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python task-auto-breakdown.py structured_prompt.yaml")
        sys.exit(1)

    # Load structured prompt
    with open(sys.argv[1], 'r') as f:
        structured_prompt = yaml.safe_load(f)

    # Execute breakdown
    breakdown = AutoTaskBreakdown(structured_prompt)
    result = breakdown.execute()

    # Output
    print("\n" + "=" * 80)
    print("📄 BREAKDOWN COMPLETE")
    print("=" * 80)
    print(yaml.dump(result, default_flow_style=False))


if __name__ == "__main__":
    main()
```

---

**VERSION:** 2.0.0
**CREATED:** 2026-02-16
**UPDATED:** 2026-02-22 — Always-Task Policy (tasks on every request, complexity ignored)
**LOCATION:** `~/.claude/memory/automatic-task-breakdown-policy.md`
**SCRIPT:** `~/.claude/memory/task-auto-breakdown.py`
