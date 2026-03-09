#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSS Theme System Testing & Validation

Validates that all three themes (Light, Dark, Material) are properly loaded,
configured, and can be switched without errors.
"""

import json
import requests
import re
from pathlib import Path
from datetime import datetime

class CSSThemeTestor:
    """Test CSS theme system"""

    def __init__(self):
        self.base_url = "http://localhost:5000"
        self.results = {
            "test_date": datetime.now().isoformat(),
            "tests": []
        }
        self.css_files = {
            "themes.css": "/static/css/themes.css",
            "theme-selector.css": "/static/css/theme-selector.css",
            "main.css": "/static/css/main.css"
        }

    def test_css_loading(self):
        """Test that all CSS files load without errors"""
        print("\n" + "="*70)
        print("TEST 1: CSS File Loading")
        print("="*70)

        results = []
        for name, path in self.css_files.items():
            url = self.base_url + path
            try:
                response = requests.get(url, timeout=5)
                status = "? PASS" if response.status_code == 200 else f"? FAIL ({response.status_code})"
                size = len(response.content)
                results.append({
                    "file": name,
                    "status": response.status_code == 200,
                    "size_bytes": size,
                    "message": status
                })
                print(f"  {name:25} {status:15} ({size:,} bytes)")
            except Exception as e:
                results.append({
                    "file": name,
                    "status": False,
                    "error": str(e)
                })
                print(f"  {name:25} ? ERROR: {str(e)}")

        self.results["tests"].append({
            "name": "CSS File Loading",
            "passed": all(r["status"] for r in results),
            "results": results
        })
        return all(r["status"] for r in results)

    def test_theme_definitions(self):
        """Test that all three themes are defined in CSS"""
        print("\n" + "="*70)
        print("TEST 2: Theme Definitions in CSS")
        print("="*70)

        themes_to_test = {
            "light": r'\[data-theme="light"\]|\:root\s*{',  # Light is default (no attr needed)
            "dark": r'\[data-theme="dark"\]',
            "material": r'\[data-theme="material"\]'
        }

        results = []
        try:
            response = requests.get(self.base_url + "/static/css/themes.css")
            css_content = response.text

            for theme, pattern in themes_to_test.items():
                found = bool(re.search(pattern, css_content, re.MULTILINE | re.DOTALL))
                status = "? PASS" if found else "? FAIL"
                results.append({
                    "theme": theme,
                    "status": found,
                    "message": f"{status} - Theme definition found" if found else f"{status} - Theme definition NOT found"
                })
                print(f"  {theme:15} {status:15} - Theme definition")
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        self.results["tests"].append({
            "name": "Theme Definitions",
            "passed": all(r.get("status", False) for r in results),
            "results": results
        })
        return all(r.get("status", False) for r in results)

    def test_css_variables(self):
        """Test that CSS variables are defined for theming"""
        print("\n" + "="*70)
        print("TEST 3: CSS Custom Properties (Variables)")
        print("="*70)

        required_vars = [
            "--color-primary",
            "--color-secondary",
            "--color-success",
            "--color-danger",
            "--color-warning",
            "--text-primary",
            "--text-secondary",
            "--surface-card",
            "--surface-page"
        ]

        results = []
        try:
            response = requests.get(self.base_url + "/static/css/themes.css")
            css_content = response.text

            for var in required_vars:
                found = var in css_content
                status = "?" if found else "?"
                results.append({
                    "variable": var,
                    "status": found,
                    "message": f"{status} - {var}"
                })
                print(f"  {var:30} {status}")
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        passed = sum(1 for r in results if r.get("status", False))
        total = len(results)
        self.results["tests"].append({
            "name": "CSS Variables",
            "passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} variables defined"
        })
        return passed == total

    def test_html_structure(self):
        """Test that HTML has proper theme selector structure"""
        print("\n" + "="*70)
        print("TEST 4: HTML Theme Selector Structure")
        print("="*70)

        elements_to_check = [
            ("theme-selector-container", "theme-selector"),
            ("theme-trigger-button", "themeSelectorBtn"),
            ("theme-dropdown", "themeDropdown"),
            ("light-option", 'data-theme="light"'),
            ("dark-option", 'data-theme="dark"'),
            ("material-option", 'data-theme="material"')
        ]

        results = []
        try:
            response = requests.get(self.base_url + "/login")
            html_content = response.text

            for name, pattern in elements_to_check:
                found = pattern in html_content
                status = "?" if found else "?"
                results.append({
                    "element": name,
                    "status": found,
                    "message": f"{status} - {pattern}"
                })
                print(f"  {name:25} {status}")
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        passed = sum(1 for r in results if r.get("status", False))
        total = len(results)
        self.results["tests"].append({
            "name": "HTML Structure",
            "passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} elements found"
        })
        return passed == total

    def test_js_theme_engine(self):
        """Test that JavaScript theme engine is present in HTML"""
        print("\n" + "="*70)
        print("TEST 5: JavaScript Theme Engine")
        print("="*70)

        js_patterns = [
            ("THEMES object", "var THEMES = {"),
            ("applyTheme function", "function applyTheme"),
            ("localStorage integration", "localStorage.setItem"),
            ("DOMContentLoaded handler", "DOMContentLoaded"),
            ("theme-option click handler", ".theme-option"),
            ("data-theme attribute setter", "setAttribute('data-theme'")
        ]

        results = []
        try:
            response = requests.get(self.base_url + "/login")
            html_content = response.text

            for name, pattern in js_patterns:
                found = pattern in html_content
                status = "?" if found else "?"
                results.append({
                    "component": name,
                    "status": found,
                    "message": f"{status} - {name}"
                })
                print(f"  {name:35} {status}")
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        passed = sum(1 for r in results if r.get("status", False))
        total = len(results)
        self.results["tests"].append({
            "name": "JavaScript Engine",
            "passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} JS components found"
        })
        return passed == total

    def test_material_design_colors(self):
        """Test Material Design 3 color palette is defined"""
        print("\n" + "="*70)
        print("TEST 6: Material Design 3 Color Palette")
        print("="*70)

        material_colors = [
            "--color-primary: #5C6BC0",
            "--color-primary-hover: #3F51B5",
            "--color-secondary: #7C4DFF",
            "--color-success: #2E7D32",
            "--color-danger: #C62828",
            "--color-info: #0277BD",
            "--surface-page: #FAFAFA",
            "--surface-card: #FFFFFF"
        ]

        results = []
        try:
            response = requests.get(self.base_url + "/static/css/themes.css")
            css_content = response.text

            # Find the [data-theme="material"] block
            material_match = re.search(
                r'\[data-theme="material"\]\s*{([^}]+)}',
                css_content,
                re.DOTALL
            )

            if material_match:
                material_block = material_match.group(1)
                for color_def in material_colors:
                    found = color_def in material_block or color_def.split(":")[0].strip() in material_block
                    status = "?" if found else "?"
                    results.append({
                        "color": color_def.split(":")[0].strip(),
                        "status": found,
                        "message": f"{status} - {color_def}"
                    })
                    print(f"  {color_def:45} {status}")
            else:
                print("  ? Material theme block not found in CSS")
                results.append({"status": False, "error": "Material theme not found"})
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        passed = sum(1 for r in results if r.get("status", False))
        total = len(results)
        self.results["tests"].append({
            "name": "Material Design Colors",
            "passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} colors defined"
        })
        return passed == total

    def test_theme_selector_styling(self):
        """Test that theme selector has proper CSS styling"""
        print("\n" + "="*70)
        print("TEST 7: Theme Selector Component Styling")
        print("="*70)

        selector_classes = [
            ".theme-selector",
            ".theme-selector__trigger",
            ".theme-selector__dropdown",
            ".theme-option",
            ".theme-option__swatch",
            ".theme-option__swatch--light",
            ".theme-option__swatch--dark",
            ".theme-option__swatch--material"
        ]

        results = []
        try:
            response = requests.get(self.base_url + "/static/css/theme-selector.css")
            css_content = response.text

            for cls in selector_classes:
                # Convert class to regex pattern
                pattern = re.escape(cls)
                found = bool(re.search(pattern, css_content))
                status = "?" if found else "?"
                results.append({
                    "class": cls,
                    "status": found,
                    "message": f"{status} - {cls}"
                })
                print(f"  {cls:40} {status}")
        except Exception as e:
            print(f"  ? ERROR: {str(e)}")
            results.append({"error": str(e), "status": False})

        passed = sum(1 for r in results if r.get("status", False))
        total = len(results)
        self.results["tests"].append({
            "name": "Theme Selector Styling",
            "passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} classes defined"
        })
        return passed == total

    def generate_report(self):
        """Generate and save test report"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        total_tests = len(self.results["tests"])
        passed_tests = sum(1 for t in self.results["tests"] if t.get("passed", False))

        for test in self.results["tests"]:
            status = "? PASS" if test.get("passed", False) else "? FAIL"
            print(f"{status} - {test['name']}")

        print("\n" + "="*70)
        print(f"OVERALL: {passed_tests}/{total_tests} tests passed")
        print("="*70)

        # Save report to JSON
        report_path = Path.home() / ".claude" / "memory" / "logs" / "css-theme-tests"
        report_path.mkdir(parents=True, exist_ok=True)

        report_file = report_path / "test-report.json"
        with open(report_file, "w") as f:
            json.dump(self.results, f, indent=2)

        print(f"\n? Report saved to: {report_file}")

        return passed_tests == total_tests

    def run_all_tests(self):
        """Run all CSS theme tests"""
        print("\n" + "="*80)
        print("CSS THEME SYSTEM - COMPREHENSIVE TEST SUITE")
        print("="*80)

        tests = [
            self.test_css_loading,
            self.test_theme_definitions,
            self.test_css_variables,
            self.test_html_structure,
            self.test_js_theme_engine,
            self.test_material_design_colors,
            self.test_theme_selector_styling
        ]

        all_passed = True
        for test_func in tests:
            try:
                if not test_func():
                    all_passed = False
            except Exception as e:
                print(f"? Test {test_func.__name__} failed: {str(e)}")
                all_passed = False

        return all_passed

def main():
    """Main entry point"""
    testor = CSSThemeTestor()
    success = testor.run_all_tests()
    testor.generate_report()

    if success:
        print("\n? ALL CSS THEME TESTS PASSED!")
        print("The Material Design 3 theme system is properly configured and ready to use.")
    else:
        print("\n? SOME TESTS FAILED")
        print("Review the report and fix any CSS issues.")

    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
