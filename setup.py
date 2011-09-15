from setuptools import setup, find_packages

setup(name='decruft',
    version='1.0.1',
    description='',
    author='Sharmila.Gopirajan',
    url='http://code.google.com/p/decruft/',
    packages=find_packages(),
    test_suite='unittest2.collector',
    install_requires=[
        'lxml',
    ],
    tests_require=[
        'unittest2',
    ],
    include_package_data=True,
)
