import io
import string

vowels = "aeiouy"
consonnants = "bcdfghjklmnpqrstvwxz"


def _mord(c: str, letters):
    return letters.index(c.lower())


def _mxor(c, k, letters):
    ko = _mord(k, string.ascii_lowercase)
    co = _mord(c, letters)
    cy = (co + ko) % len(letters)
    return letters[cy]


def _amxor(c, k, letters):
    ko = _mord(k, string.ascii_lowercase)
    co = _mord(c, letters)
    cy = (co - ko) % len(letters)
    return letters[cy]


def cipher(text, key, xor=_mxor):
    out = io.StringIO()
    for i, c in enumerate(text):
        if c.lower() not in string.ascii_lowercase:
            out.write(c)
            continue
        k = key[i % len(key)]
        cy = xor(c, k, vowels if c.lower() in vowels else consonnants)
        if c.isupper():
            cy = cy.upper()
        out.write(cy)
    return out.getvalue()


def decipher(text, key):
    return cipher(text, key, xor=_amxor)
