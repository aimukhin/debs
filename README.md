# debs
A simple web-based double-entry bookkeeping system.

## Features
- Supports equity, assets, liabilities, income, and expenses accounts.
- Currency-agnostic.
- Arbitrary-precision integer arithmetic.
- Encrypted database.

## Description
The program is a WSGI application written in Python 3. If available, it
uses SQLCipher for data storage. Otherwise, it defaults to plain SQLite.

## Screenshots
### The list of accounts:
![](docs/list.png)
### An account page:
![](docs/acct.png)

## Setup
Pass a path to the database file in the `DB` environment variable.

## Customization
Decimal point, thousand separator, and style sheet are easily
customized.

## Note
For performance reasons, the program does not support SQLCipher
passphrases, but asks instead for raw keys, expected as 64-character
strings of hexadecimal digits.

## Compliance
The program produces an HTML5 markup with a CSS3 style sheet.

## License
MIT.
