import importlib.util

from setuptools import setup

# Single source of truth: import __version__ from pyconfix/_version.py directly
# (that module has no imports of its own, so this does not pull in the package).
_spec = importlib.util.spec_from_file_location("pyconfix_version", "pyconfix/_version.py")
_version_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_version_module)

setup(
    name="pyconfix",
    version=_version_module.__version__,
    description="A simple feature managment tool library",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nemesis",
    author_email="nemesiswasalientoo@proton.me",
    url="https://github.com/NemesisWasAlienToo/pyconfix",
    packages=["pyconfix"],
    python_requires=">=3.11",
    license="MIT",
    install_requires=[
        "windows-curses ; platform_system == 'Windows'"
    ],
    entry_points={
        'console_scripts': [
            'pyconfix = pyconfix.__main__:main',
        ],
    },
)