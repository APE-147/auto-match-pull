#!/usr/bin/env python3
"""
Setup script for auto-match-pull package
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    try:
        with open('README.md', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Auto Match Pull - 自动匹配文件夹和Git仓库并定时同步"

# Read requirements
def read_requirements():
    try:
        with open('requirements.txt', 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

setup(
    name='auto-match-pull',
    version='1.0.0',
    description='自动匹配文件夹和Git仓库并定时同步',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    author='APE-147',
    author_email='your-email@example.com',
    url='https://github.com/APE-147/auto-match-pull',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Version Control :: Git',
        'Topic :: System :: Filesystems',
        'Topic :: Utilities',
    ],
    keywords='git, automation, folder, repository, sync, pull',
    python_requires='>=3.8',
    install_requires=read_requirements(),
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=4.0.0',
            'black>=22.0.0',
            'flake8>=5.0.0',
            'mypy>=1.0.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'auto-match-pull=auto_match_pull.cli:main',
            'amp=auto_match_pull.cli:main',
        ],
    },
    include_package_data=True,
    zip_safe=False,
    project_urls={
        'Bug Reports': 'https://github.com/APE-147/auto-match-pull/issues',
        'Source': 'https://github.com/APE-147/auto-match-pull',
        'Documentation': 'https://github.com/APE-147/auto-match-pull/blob/main/README.md',
    },
)