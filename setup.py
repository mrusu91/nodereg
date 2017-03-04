from setuptools import find_packages, setup
from os import path


here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.rst'), encoding='utf-8') as _file:
    long_description = _file.read()

setup(
    name='nodereg',
    version='0.1.0',
    description='Cluster node registration tool',
    long_description=long_description,
    url='https://github.com/viruxel/nodereg',
    author='Marian Rusu',
    author_email='rusumarian91@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Installation/Setup'
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords='cluster node instance registration',
    packages=find_packages(),
    install_requires=[
        'boto',
        'PyYAML',
        'tinycert>=0.2.0',
    ],
    setup_requires=[
        'pytest-runner',
    ],
    tests_require=[
        'moto',
        'pytest',
    ],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'nodereg = nodereg.run:main',
        ],
    },
)
