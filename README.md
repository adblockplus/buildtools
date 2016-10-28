# Buildtools

## Introduction

Tools used to produce builds and releases of the Adblock Plus browser
extensions. Intended to be used as a dependency by the extension repositories,
not directly.


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
