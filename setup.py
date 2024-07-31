#!/usr/bin/env python

from distutils.core import setup

setup(
    name="mushroom",
    version="0.3",
    description="A new MUSH server",
    author="Paul Mathieu",
    author_email="paul@ponteilla.net",
    url="https://github.com/po1/mushroom",
    packages=["mushroom"],
    entry_points={
        "console_scripts": ["mushroomd=mushroom.server:main"],
    },
    install_requires=[
        "tomli",
        "websockets",
    ],
)
