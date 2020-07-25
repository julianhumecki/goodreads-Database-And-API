import os
import requests
from bs4 import BeautifulSoup as BeautifulSoup
import string


from flask import Flask, render_template, request, session, redirect,abort,jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("POSTGRES_SERVER_CREDENTIALS"))
db = scoped_session(sessionmaker(bind=engine))

#TODO############################
#add ability for users on my site to edit reviews on book page!
#abstract cache to be its own object
#Cache.max_size, Cache.current_size 


class Query:
	def __init__(self, query_result):
		self.query_ret = query_result
		self.limit = 10
	def isNone(self):
		return self.query_ret is None
	def limitN(self):
		if self.isNone():
			return None

		count = 0
		topN = list()
		for res in self.query_ret:
			if count < self.limit:
				topN.append(res)
			else:
				break
			count += 1
		return topN
	def getN(self):
		return self.limit



@app.route("/",methods=['GET'])
def index():
	if not isLoggedIn():
		return redirect("/login", code=302)
	#print(session["username"])
	#input("")
	return render_template('index.html', signed_in=session['username'])

@app.route("/search",methods=['GET','POST'])
def search():
	if not isLoggedIn():
		return redirect("/login", code=302)
	#implement a search
	search_results = []
	start_close_author = None
	isEmpty = False
	if request.method == "POST":
		info_entered = str(request.form.get("search-term")).lower()
	
		search_by_author = Query(db.execute("SELECT * from books where POSITION(:susan in author)>0;" , {"susan": info_entered}).fetchall())
		search_by_title = Query(db.execute("SELECT * from books where POSITION(:susan in title)>0;" , {"susan": info_entered}).fetchall())
		search_by_isbn = Query(db.execute("SELECT * from books where POSITION(:susan in isbn)>0;" , {"susan": info_entered}).fetchall())
		
		search_results = {'author':search_by_author.limitN(), 'title':search_by_title.limitN(), 'isbn':search_by_isbn.limitN()}
		
		start_close_author = get_close_pairs(search_by_author.getN())
		isEmpty = len(search_by_author.limitN()) == 0 and len(search_by_title.limitN()) == 0 and len(search_by_isbn.limitN()) == 0

	return render_template('search.html', search_results=search_results, start_close=start_close_author,empty=isEmpty, signed_in=session['username'])

#this route will be for your reviews

@app.route("/reviews",methods=['GET'])
def reviews():
	if not isLoggedIn():
		return redirect("/login", code=302)
	session['my_reviews'] = get_my_reviews()
	
	return render_template('reviews.html', signed_in=session['username'], reviews=session['my_reviews'])


@app.route("/api/<isbn>",methods=['GET'])
def api(isbn):
	if not isLoggedIn():
		return redirect("/login", code=302)

	book_info = db.execute("SELECT * from books where isbn = :isbn",{"isbn":isbn}).fetchone()
	#if dne
	if not book_info:
		abort(404)
	#return a json object with my review count and average rating
	average_rating = db.execute("SELECT to_char( AVG(rating), '99999999999999999D999') as average_amount from reviewdata where isbn = :isbn;",{"isbn":isbn}).fetchone()
	total_count = db.execute(" SELECT COUNT(*) as count from reviewdata where isbn=:isbn;",{"isbn":isbn}).fetchone()
	if total_count[0] == 0:
		average_rating = "N/A"
	else:
		average_rating = average_rating[0].strip()
	
	return jsonify({
		"title": book_info[1],
    	"author": book_info[2],
    	"year": book_info[3],
    	"isbn": book_info[0],
    	"review_count": total_count[0],
    	"average_score": average_rating
	})

@app.route("/book/<isbn>", methods=["GET","POST","PUT"])
def book(isbn):
	if not isLoggedIn():
		return redirect("/login", code=302)

	if request.method == "POST":
		rating = request.form.get("rating")
		comment = str(request.form.get("comment"))
		method = str(request.form.get("_METHOD"))
		#if requested method is a put method
		if (method == "PUT"):
			db.execute("UPDATE reviewdata SET rating = :rating, review = :comment WHERE username=:username AND isbn=:isbn",
			{"rating":rating, "comment":comment,"username":session['username'],"isbn":isbn})
			db.commit()
			return redirect("/book/"+str(isbn))

		db.execute("INSERT INTO reviewdata (username, isbn, rating, review) VALUES (:username, :isbn, :rating, :review)",
                {"username":session['username'],"isbn": isbn, "rating": rating, "review":comment})
		db.commit()
		return redirect("/book/"+str(isbn))
	else:
		cache_size = 50
		result = check_if_already_cached(isbn)
		book_with_isbn = db.execute("SELECT * from books where isbn = :isbn;", {"isbn": isbn}).fetchone()

		if result == None:
			#if found
			#IMPLEMENT A CACHE
			if not book_with_isbn == None:
				
				
				res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": os.getenv("goodreads_api"), "isbns": isbn})
				json = res.json()
				average_rating = json['books'][0]['average_rating']
				number_ratings = json['books'][0]['work_ratings_count']
				url = extract_image(book_with_isbn[1])

				if len(session['cache']) < cache_size:
					session['cache'].append([isbn, average_rating,number_ratings,url])
				else:
					session['cache'].pop(0)
					session['cache'].append([isbn, average_rating,number_ratings,url])
			else:
				average_rating = None
				url = None
				number_ratings = None
				return render_template("book_info.html",book=book_with_isbn, average_rating=average_rating, url=url, number_ratings=number_ratings,signed_in=session['username'])

		else:
			average_rating = result[1]
			number_ratings = result[2]
			url = result[3]

		#get the latest reviews for this isbn
		reviews_with_isbn = db.execute("SELECT * from reviewdata where isbn=:isbn order by id desc;",{"isbn":book_with_isbn[0]}).fetchall()
		can_add_review,data = find_in_existing_reviews(reviews_with_isbn)
		
		return render_template("book_info.html",book=book_with_isbn, average_rating=average_rating, url=url, number_ratings=number_ratings,signed_in=session['username'], reviews=reviews_with_isbn, add_review=can_add_review, my_review=data)


   


@app.route("/login", methods=["GET", "POST"])
def login():
    #already logged in, shouldnt have access to log in form
	if isLoggedIn():
		return redirect("/", code=302)
	#check if anyone logged in
	if session.get("username") == None:
		config_sessions()
		print(session['username'])
	if request.method == "POST":
		username =  str(request.form.get("username"))
		password = str(request.form.get("password"))
		result = db.execute("SELECT firstname, email, password FROM users WHERE email = :username", {"username":username}).fetchone()
		if result is None:
			#input("USER DNE")
			return render_template("login.html", error="Username DNE")
		elif not result.password == password:
			#input("Wrong pass")
			return render_template("login.html", error="Invalid Password")
		else:
			#input("Logging...")
			session["username"] = result.email
			session["firstname"] = result.firstname
			session["welcome_message"] = "Signed in as: " + session["firstname"]
			#get my_reviews
			session["my_reviews"] = get_my_reviews()

			return redirect("/", code=302)

	return render_template("login.html", signed_in=session["username"], navbar=session["welcome_message"])

@app.route("/register", methods=["GET","POST"])
def register():
    #if already logged in, the user shouldn't have access to register form
    if isLoggedIn():
        return redirect("/", code=302)

    if session.get("username") == None:
        config_sessions()

    #--------------------------------------------------------

    register = ""
    if request.method == "POST":
        firstName = str(request.form.get("firstName"))
        lastName = str(request.form.get("lastName"))
        email = str(request.form.get("email"))
        password = str(request.form.get("password"))  
        reviews = []
        #check for preexisiting that's been registered
        existingInfo = db.execute("SELECT email FROM users WHERE email = :email", {"email":email}).fetchone()
        if existingInfo == None:
            db.execute("INSERT INTO users (reviews,firstname, lastname, email, password) VALUES (:reviews, :firstname, :lastname, :email, :password)",
                {"reviews":reviews,"firstname": firstName, "lastname":lastName, "email":email, "password":password})

            db.commit()
            register = "Success"
        else:
            register = "Email is already registered"
            return render_template("register.html", register=register, signed_in=session["username"], navbar=session["welcome_message"])
        

    return render_template("register.html", register=register, signed_in=session["username"], navbar=session["welcome_message"])

@app.route("/logout")
def logout():
    config_sessions()
    return redirect("/login", code=302)

def config_sessions():
	session['cache'] = list()
	session["username"] = None
	session["firstname"] = None
	session["my_reviews"] = []
	session['welcome_message'] = None

def isLoggedIn():
    if session.get("username") is None:
        return False
    return True

#functionality functions unrelated to routing/logging in
def get_my_reviews():
	result = db.execute("SELECT * FROM reviewdata WHERE username = :username order by id desc;", {"username":session['username']}).fetchall()
	return result;

def check_if_already_cached(isbn):
	for value in session['cache']:
		if value[0] == isbn:
			return value
	return None

def get_close_pairs(n):
	starts = list()
	ends = list()
	for i in range(0, n, 3):
		start,end = i, i+3
		starts.append(start)
		ends.append(end)
	ends.pop()
	ends.append(n)
	return (starts, ends)

def extract_image(title):
	
	adlt = 'moderate' # can be set to 'moderate'
	sear=title.strip()
	sear=sear.replace(' ','+')
	URL='https://bing.com/images/search?q=' + sear + '&safeSearch=' + adlt
#	print(URL)
	USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:65.0) Gecko/20100101 Firefox/65.0"
	headers = {"user-agent": USER_AGENT}
	resp = requests.get(URL, headers=headers)
	results=[]
	soup = BeautifulSoup(resp.content, "html.parser")

	#wow = soup.find_all('img',class_='mimg')
	wow = soup.find_all('img', class_="mimg")

	for i in wow:
		try:
			return i['data-src']
		except:
			pass

	return None

def find_in_existing_reviews(reviews_with_isbn):
	for review in reviews_with_isbn:
		if review[1] == session['username']:
			return (False,review)
	return (True,None)