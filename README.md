# debs
A simple web-based double-entry bookkeeping system.

## Features
The system supports all basic account types, and works with arbitrary big numbers using precise integer arithmetic.

## Requirements
The program is written in Python 3 and intended to be run by a web server as a WSGI application. It uses SQLite for data storage.

## Install
Arrange your web server to run the program as a WSGI application. Put the database file wherever you like, only make sure the database file and its parent directory are writable by the user from whom the web server is running. In the Python source set the path to the database file. You might also wish to modify thousand and decimal separators to match your locale.

## Screenshots
### The list of accounts:
![28541212-db3ee04a-70c0-11e7-8915-497f638fd01b](https://user-images.githubusercontent.com/29631214/29485252-690aab78-84d7-11e7-940b-615b87a9f251.jpg)
### An account page:
![28541213-db4139e4-70c0-11e7-903e-c4f71dc3b427](https://user-images.githubusercontent.com/29631214/29485251-690a8d78-84d7-11e7-844d-95527f026758.jpg)
