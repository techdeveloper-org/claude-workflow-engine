"""
Setup configuration for Claude Workflow Engine
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / 'README.md'
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ''

# Read requirements
requirements_file = Path(__file__).parent / 'requirements.txt'
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.startswith('#')
    ]

setup(
    name='claude-workflow-engine',
    version='5.6.0',
    description='3-Level LangGraph orchestration pipeline for Claude Code workflows',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='TechDeveloper',
    author_email='',
    url='https://github.com/techdeveloper-org/claude-workflow-engine',
    license='MIT',

    # Package configuration
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    include_package_data=True,

    # Dependencies
    install_requires=requirements,
    python_requires='>=3.8',

    # Entry points
    entry_points={
        'console_scripts': [
            'claude-workflow=scripts.3-level-flow:main',
        ],
    },

    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Software Development :: Build Tools',
    ],

    keywords='claude ai workflow langgraph orchestration pipeline automation',
    project_urls={
        'Documentation': 'https://github.com/techdeveloper-org/claude-workflow-engine/docs',
        'Source': 'https://github.com/techdeveloper-org/claude-workflow-engine',
        'Tracker': 'https://github.com/techdeveloper-org/claude-workflow-engine/issues',
    },
)
