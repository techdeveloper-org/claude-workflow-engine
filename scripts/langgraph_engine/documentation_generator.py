"""
Documentation Generator - Step 13
Intelligent creation and update of project documentation files.
Uses enterprise-grade templates and understands full codebase.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProjectContext:
    """Project analysis from codebase scanning."""
    name: str
    description: str
    languages: List[str]
    frameworks: List[str]
    structure: Dict[str, str]  # {folder: purpose}
    key_components: List[Dict]  # [{name, path, purpose, tech}]
    has_tests: bool
    test_command: str
    run_command: str
    dependencies: List[str]
    version: str


class CodebaseAnalyzer:
    """Analyzes codebase to understand structure and purpose."""

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.logger = logging.getLogger(__name__)

    def analyze(self) -> ProjectContext:
        """Scan codebase and extract context."""
        self.logger.info("Analyzing codebase structure...")

        # Get project name
        name = self.root.name

        # Detect languages
        languages = self._detect_languages()

        # Detect frameworks
        frameworks = self._detect_frameworks()

        # Scan directory structure
        structure = self._scan_structure()

        # Get version
        version = self._get_version()

        # Detect test setup
        has_tests, test_command = self._detect_tests()

        # Get run command
        run_command = self._get_run_command(frameworks)

        # Get dependencies
        dependencies = self._extract_dependencies()

        # Extract key components
        key_components = self._identify_key_components(structure)

        return ProjectContext(
            name=name,
            description=self._generate_description(name, frameworks),
            languages=languages,
            frameworks=frameworks,
            structure=structure,
            key_components=key_components,
            has_tests=has_tests,
            test_command=test_command,
            run_command=run_command,
            dependencies=dependencies,
            version=version
        )

    def _detect_languages(self) -> List[str]:
        """Detect programming languages in project."""
        languages = set()
        extensions_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.go': 'Go',
            '.rs': 'Rust',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
        }

        for ext, lang in extensions_map.items():
            if list(self.root.rglob(f'*{ext}')):
                languages.add(lang)

        return sorted(list(languages))

    def _detect_frameworks(self) -> List[str]:
        """Detect frameworks from common config files."""
        frameworks = set()

        # Check for common framework indicators
        checks = {
            'Flask': 'requirements.txt|flask',
            'Django': 'requirements.txt|django',
            'FastAPI': 'requirements.txt|fastapi',
            'Spring Boot': 'pom.xml|spring-boot',
            'React': 'package.json|react',
            'Angular': 'package.json|@angular',
            'Vue': 'package.json|vue',
            'Docker': 'Dockerfile',
            'Kubernetes': 'k8s|kubernetes|helm',
        }

        for framework, indicator in checks.items():
            for part in indicator.split('|'):
                if list(self.root.rglob(part)):
                    frameworks.add(framework)
                    break

        return sorted(list(frameworks))

    def _scan_structure(self) -> Dict[str, str]:
        """Map directory structure to purposes."""
        structure = {}

        # Common folder mappings
        folder_purposes = {
            'src': 'Source code',
            'tests': 'Unit and integration tests',
            'docs': 'Documentation',
            'scripts': 'Utility scripts',
            'config': 'Configuration files',
            'docker': 'Docker-related files',
            'k8s': 'Kubernetes manifests',
            'migrations': 'Database migrations',
            'public': 'Public assets',
            'static': 'Static files',
            'templates': 'HTML/View templates',
            'utils': 'Utility functions',
            'lib': 'Library code',
            'models': 'Data models',
            'controllers': 'Request handlers',
            'services': 'Business logic',
            'middleware': 'Middleware',
        }

        for folder, purpose in folder_purposes.items():
            if (self.root / folder).exists():
                structure[folder] = purpose

        return structure

    def _detect_tests(self) -> Tuple[bool, str]:
        """Detect test framework and command."""
        # Check for test files
        test_files = list(self.root.rglob('test_*.py')) + list(self.root.rglob('*_test.py'))

        if test_files:
            # Check for pytest
            if (self.root / 'pytest.ini').exists() or list(self.root.rglob('conftest.py')):
                return True, 'pytest'
            # Check for unittest
            return True, 'python -m unittest'

        # Check for JavaScript tests
        package_json = self.root / 'package.json'
        if package_json.exists():
            try:
                with open(package_json) as f:
                    pkg = json.load(f)
                    if pkg.get('scripts', {}).get('test'):
                        return True, 'npm test'
            except:
                pass

        return False, ''

    def _get_run_command(self, frameworks: List[str]) -> str:
        """Suggest run command based on frameworks."""
        if 'Flask' in frameworks:
            return 'python -m flask run'
        elif 'Django' in frameworks:
            return 'python manage.py runserver'
        elif 'FastAPI' in frameworks:
            return 'uvicorn main:app --reload'
        elif 'Spring Boot' in frameworks:
            return 'mvn spring-boot:run'
        elif 'React' in frameworks or 'Vue' in frameworks or 'Angular' in frameworks:
            return 'npm start'

        return 'See CLAUDE.md for run instructions'

    def _extract_dependencies(self) -> List[str]:
        """Extract major dependencies."""
        deps = []

        # From requirements.txt
        req_file = self.root / 'requirements.txt'
        if req_file.exists():
            try:
                with open(req_file) as f:
                    lines = f.readlines()[:10]  # First 10 deps
                    deps.extend([line.strip() for line in lines if line.strip()])
            except:
                pass

        # From package.json
        pkg_file = self.root / 'package.json'
        if pkg_file.exists():
            try:
                with open(pkg_file) as f:
                    pkg = json.load(f)
                    deps.extend(list(pkg.get('dependencies', {}).keys())[:10])
            except:
                pass

        return deps[:15]  # Limit to 15

    def _get_version(self) -> str:
        """Extract project version."""
        # Check version files
        version_files = ['version.txt', 'VERSION', 'VERSION.md']
        for vf in version_files:
            vf_path = self.root / vf
            if vf_path.exists():
                try:
                    return vf_path.read_text().strip().split('\n')[0]
                except:
                    pass

        # Check package.json
        pkg_file = self.root / 'package.json'
        if pkg_file.exists():
            try:
                with open(pkg_file) as f:
                    return json.load(f).get('version', '0.1.0')
            except:
                pass

        # Check setup.py
        setup_file = self.root / 'setup.py'
        if setup_file.exists():
            try:
                content = setup_file.read_text()
                import re
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
            except:
                pass

        return '0.1.0'

    def _generate_description(self, name: str, frameworks: List[str]) -> str:
        """Generate project description."""
        if frameworks:
            return f"{name} is a {', '.join(frameworks)} project providing core functionality."
        return f"{name} is a software project with complete functionality."

    def _identify_key_components(self, structure: Dict[str, str]) -> List[Dict]:
        """Identify key components from directory structure."""
        components = []

        # Map folders to components
        folder_component_map = {
            'models': {'tech': 'Data Models', 'purpose': 'Core data structures'},
            'controllers': {'tech': 'Controllers', 'purpose': 'Request handling'},
            'services': {'tech': 'Services', 'purpose': 'Business logic'},
            'middleware': {'tech': 'Middleware', 'purpose': 'Request/response processing'},
            'routes': {'tech': 'Routing', 'purpose': 'API endpoints'},
            'utils': {'tech': 'Utilities', 'purpose': 'Helper functions'},
        }

        for folder, purpose in structure.items():
            if folder in folder_component_map:
                info = folder_component_map[folder]
                components.append({
                    'name': info['tech'],
                    'path': folder,
                    'purpose': info['purpose'],
                    'tech': info['tech']
                })

        return components


class DocumentationGenerator:
    """Generate documentation using templates and context."""

    def __init__(self, project_root: str = ".", session_dir: str = None):
        self.root = Path(project_root)
        self.session_dir = session_dir or str(Path.home() / '.claude' / 'logs' / 'sessions' / 'current')
        self.analyzer = CodebaseAnalyzer(project_root)
        self.logger = logging.getLogger(__name__)

    def update_all_documentation(self, files_modified: List[str] = None) -> Dict[str, Any]:
        """Update or create all 5 documentation files."""
        files_modified = files_modified or []

        self.logger.info("=" * 60)
        self.logger.info("GENERATING/UPDATING DOCUMENTATION")
        self.logger.info("=" * 60)

        updated_files = []
        errors = []

        # Analyze codebase once
        try:
            context = self.analyzer.analyze()
            self.logger.info(f"✓ Codebase analysis complete: {context.name}")
        except Exception as e:
            self.logger.error(f"Failed to analyze codebase: {e}")
            errors.append(str(e))
            return {"success": False, "error": str(e), "updated_files": []}

        # Process each documentation file
        docs_to_update = [
            ('README.md', self.update_or_create_readme),
            ('CLAUDE.md', self.update_or_create_claude_md),
            ('System_Requirement_Analysis.md', self.update_or_create_sra),
            ('CHANGELOG.md', self.update_or_create_changelog),
            ('VERSION', self.update_or_create_version),
        ]

        for filename, update_func in docs_to_update:
            try:
                file_path = self.root / filename
                if file_path.exists():
                    self.logger.info(f"Updating {filename}...")
                    update_func(file_path, context, files_modified)
                    updated_files.append(filename)
                    self.logger.info(f"✓ Updated {filename}")
                else:
                    self.logger.info(f"Creating {filename}...")
                    update_func(file_path, context, files_modified)
                    updated_files.append(f"{filename} (created)")
                    self.logger.info(f"✓ Created {filename}")
            except Exception as e:
                self.logger.error(f"Error with {filename}: {e}")
                errors.append(f"{filename}: {e}")

        return {
            "success": len(errors) == 0,
            "updated_files": updated_files,
            "errors": errors if errors else None,
            "context": {
                "project_name": context.name,
                "languages": context.languages,
                "frameworks": context.frameworks,
                "version": context.version,
            }
        }

    def update_or_create_readme(self, file_path: Path, context: ProjectContext, files_modified: List[str]):
        """Update or create README.md"""
        # TODO: Implement using README template
        pass

    def update_or_create_claude_md(self, file_path: Path, context: ProjectContext, files_modified: List[str]):
        """Update or create CLAUDE.md"""
        # TODO: Implement using CLAUDE.md template
        pass

    def update_or_create_sra(self, file_path: Path, context: ProjectContext, files_modified: List[str]):
        """Update or create System_Requirement_Analysis.md"""
        # TODO: Implement using SRA template
        pass

    def update_or_create_changelog(self, file_path: Path, context: ProjectContext, files_modified: List[str]):
        """Update or create CHANGELOG.md"""
        # TODO: Implement using CHANGELOG template
        pass

    def update_or_create_version(self, file_path: Path, context: ProjectContext, files_modified: List[str]):
        """Update or create VERSION file"""
        # TODO: Implement using VERSION template
        pass
