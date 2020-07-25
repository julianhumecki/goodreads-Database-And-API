import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Reviews(db.Model):
    __tablename__ = "reviewdata"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False)
    isbn = db.Column(db.String, nullable=False)
    rating = db.Column(db.Float,nullable=False)
    review = db.Column(db.String, nullable=False)

# class Users(db.Model):
#     __tablename__ = "users"
#     id = db.Column(db.Integer, primary_key=True)
#     #no need for reviews
#     reviews = db.Column(db.ARRAY(db.Integer), nullable=True)
#     firstname = db.Column(db.String, nullable=False)
#     lastname = db.Column(db.String, nullable=False)
#     #update, delete and update tables
#     email = db.Column(db.String, nullable=False)
#     #basically given an id linking to logins table id
#     password = db.Column(db.String, nullable=False)




