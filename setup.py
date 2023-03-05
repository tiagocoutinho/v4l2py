#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

"""The setup script."""

from setuptools import setup, find_packages


with open("README.md") as f:
    readme = f.read()


setup(
    name="v4l2py",
    version="2.0.1",
    author="Jose Tiago Macara Coutinho",
    author_email="coutinhotiago@gmail.com",
    license="GPLv3",
    keywords="v4l2, video4linux, video4linux2, human",
    description="Human friendly video for linux",
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Video",
        "Topic :: Multimedia :: Video :: Capture",
    ],
    url="http://pypi.python.org/pypi/v4l2py",
    project_urls={
        "Documentation": "https://github.com/tiagocoutinho/v4l2py",
        "Source": "https://github.com/tiagocoutinho/v4l2py",
    },
)
