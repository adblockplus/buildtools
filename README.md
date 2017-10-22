# Buildtools

## Introduction

Tools used to produce builds and releases of the Adblock Plus browser
extensions. Intended to be used as a dependency by the extension repositories,
not directly.

## Requirements

- [The Jinja2 module](http://jinja.pocoo.org/docs) (>= 2.8)
- [The Pycrypto module](http://pythonhosted.org/pycrypto/) (>= 2.6.1)

## Usage

Please refer to the documentation of the extension repositories for usage
instructions.


## Tests

As per the [Python Coding Style guide](https://adblockplus.org/en/coding-style#python)
this repository can be linted and tested using [Tox](https://pypi.python.org/pypi/tox).

Once [Tox is installed](https://tox.readthedocs.io/en/latest/install.html) it's
easy to lint and run the tests:

    tox

_(Tox will take care of installing the other dependencies such as flake8 and
flake8-abp inside a virtualenv.)_

For more information about the unit tests please refer to tests/README.md.
