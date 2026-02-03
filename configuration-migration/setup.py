"""Setup script for Custom Events Migrator package."""

import os
from setuptools import setup, find_packages

# Read the version from pyproject.toml to ensure consistency
version = "1.0.0"  # Default version

# Read the long description from README.md
with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="instana-configuration-migration",
    version=version,
    description="A comprehensive tool for migrating Instana configurations between different environments, instances, and organizations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Instana Team",
    author_email="support@instana.com",
    url="https://github.ibm.com/instana/automation-with-apis",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "urllib3>=2.0.0",
        "configparser>=5.3.0",
        "instana_client>=1.0.0",
        "aiohttp>=3.9.0",
        "aiohttp-retry>=2.8.3",
    ],
    entry_points={
        "console_scripts": [
            "instana-migrate=cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    ],
    python_requires=">=3.8",
    include_package_data=True,
)

# Made with Bob
