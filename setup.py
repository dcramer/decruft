import os
from setuptools import setup, find_packages

setup(name='decruft',
    version='1.0.1',
    description='',
    author='Sharmila.Gopirajan',
    url='http://code.google.com/p/decruft/',
    packages=find_packages(),
    install_requires=[
        'lxml',
    ],
    include_package_data=True,
)
