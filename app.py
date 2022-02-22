import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from helpers import apology, login_required, lookup, usd
from pytz import timezone

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

    
# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    id = session["user_id"]
    rows = db.execute("SELECT * FROM users WHERE id = ?", id)
    stockrows = db.execute("SELECT * FROM stock WHERE user_id = ?", id)
    listDicStocks = []
    for stockrow in stockrows:
        dic = lookup(stockrow["symbol"])
        dic["shares"] = stockrow["shares"]
        listDicStocks.append(dic)
    return render_template("index.html", rows=rows[0], listDicStocks=listDicStocks)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        dic = lookup(request.form.get("symbol"))

        if dic is None:
            return apology("Invalid symbol", 400)

        shares = request.form.get("shares")

        if not shares:
            return apology("missing shares", 400)
        id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = ?", id)

        if float(rows[0]["cash"]) < (float(dic["price"]) * float(shares)):
            return apology("Can't afford", 400)
        cash = float(rows[0]["cash"]) - (float(dic["price"]) * float(shares))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", str(round(cash, 2)) , id)

        rows = db.execute("SELECT * FROM stock WHERE user_id = ? AND symbol = ?", id, dic["symbol"])
        if len(rows) == 0:
            db.execute("INSERT INTO stock (user_id, symbol, shares) VALUES(?, ?, ?)",id ,dic["symbol"], int(shares))
        else:
            db.execute("UPDATE stock SET shares = ?", int(shares) + int(rows[0]["shares"]))

        now = datetime.now(timezone('America/New_york'))
        db.execute("INSERT INTO history (user_id, symbol, shares, price, date) VALUES(?, ?, ?, ?, ?)",id ,dic["symbol"], shares, dic["price"], now.strftime('%Y-%m-%d %H:%M:%S'))

        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    id = session["user_id"]
    rows = db.execute("SELECT * FROM history WHERE user_id = ?", id)
    if len(rows) == 0 :
        return apology("no history", 400)
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        dic = lookup(request.form.get("symbol"))
        if dic is None:
            return apology("Invalid symbol", 400)
        return render_template("quoted.html", dic=dic)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        username = request.form.get("username")
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if not username:
            return apology("must provide username", 403)
        elif len(rows) == 1:
            return apology("Sorry, the username is already taken", 403)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Sorry, your password didn't match", 403)
        elif len(request.form.get("password")) < 8:
            return apology("Sorry, your password must at least have 8 charecters", 400)

        contains_digit, contains_char = False, False
        for character in str(request.form.get("password")):
            if character.isdigit():
                contains_digit = True
            if character.isalpha():
                contains_char = True
        if contains_digit == False:
            return apology("Sorry, your password must contain combination between letters and numbers", 400)
        elif contains_char == False:
            return apology("Sorry, your password must contain combination between letters and numbers", 400)

        hash_password = generate_password_hash(request.form.get("password"))

        id = db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",username ,hash_password)

        session["user_id"] = id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbol = set()

    id = session["user_id"]
    rows = db.execute("SELECT symbol FROM stock WHERE user_id = ?", id)

    for row in rows:
        symbol.add(row["symbol"])

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Missing symbol", 400)

        if request.form.get("symbol") not in symbol:
            return apology("Symbol not owned", 400)

        if not request.form.get("shares"):
            return apology("Missing shares", 400)

        x = db.execute("SELECT shares FROM stock WHERE user_id = ? AND symbol = ?", id, request.form.get("symbol"))

        if int(request.form.get("shares")) > int(x[0]["shares"]):
            return apology("too many shares", 400)

        price = lookup(request.form.get("symbol"))
        cash = int(price["price"]) * int(request.form.get("shares"))
        roww = db.execute("SELECT cash FROM users WHERE id = ?", id)
        acash = roww[0]["cash"]
        db.execute("UPDATE users SET cash = ? WHERE id = ?", float(acash) + float(cash) , id)
        share = int(x[0]["shares"]) - int(request.form.get("shares"))

        if share == 0:
            db.execute("DELETE FROM stock WHERE user_id = ?", id)
        else:
            db.execute("UPDATE stock SET shares = ? WHERE user_id = ?", share, id)
        now = datetime.now(timezone('America/New_york'))
        db.execute("INSERT INTO history (user_id, symbol, shares, price, date) VALUES(?, ?, ?, ?, ?)",id ,price["symbol"], -share, price["price"], now.strftime('%Y-%m-%d %H:%M:%S'))

        return redirect("/")
    else:
        return render_template("sell.html", symbol=symbol)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
