import os
import json
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room
from google import genai
from google.genai import types

app = Flask(__name__)
app.config['SECRET_KEY'] = 'skillsphere_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


# ------------------ Models ------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anonymous_name = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    skills_offered = db.Column(db.Text, nullable=True)
    skills_wanted = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=0.0)
    completed_exchanges = db.Column(db.Integer, default=0)
    trust_score = db.Column(db.Integer, default=50)
    is_admin = db.Column(db.Boolean, default=False)
    avatar = db.Column(db.String(50), default='🧠')
    bio = db.Column(db.String(250), default='')
    badge = db.Column(db.String(100), default='New Explorer')


class SessionBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    session_date = db.Column(db.String(20), nullable=False)
    session_time = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_sessions')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_sessions')


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_booking.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship('SessionBooking', backref='reviews')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='given_reviews')
    reviewee = db.relationship('User', foreign_keys=[reviewee_id], backref='received_reviews')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    replies = db.relationship('Message', backref=db.backref('parent', remote_side=[id]), lazy=True)


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    favorite_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='favorites_made')
    favorite_user = db.relationship('User', foreign_keys=[favorite_user_id], backref='favorited_by')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'favorite_user_id', name='unique_favorite_pair'),
    )


class SkillPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_type = db.Column(db.String(20), nullable=False)
    skill_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    availability = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), default='Open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='skill_posts')


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session_booking.id'), nullable=False)
    skill = db.Column(db.String(200), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='certificates')
    partner = db.relationship('User', foreign_keys=[partner_id])
    session = db.relationship('SessionBooking')

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    skill = db.Column(db.String(100), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(300), nullable=False)
    option2 = db.Column(db.String(300), nullable=False)
    option3 = db.Column(db.String(300), nullable=False)
    option4 = db.Column(db.String(300), nullable=False)
    correct_answer = db.Column(db.String(300), nullable=False)
    source = db.Column(db.String(50), default='AI')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    skill = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='quiz_results')

class LearningCertificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    skill = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    date_earned = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='learning_certificates')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------ Helper Functions ------------------

def convert_skills_to_set(skill_text):
    if not skill_text:
        return set()
    return {skill.strip().lower() for skill in skill_text.split(',') if skill.strip()}


def update_user_rating(user_id):
    user = User.query.get(user_id)
    if not user:
        return

    reviews = Review.query.filter_by(reviewee_id=user_id).all()
    if reviews:
        total = sum(review.stars for review in reviews)
        user.rating = round(total / len(reviews), 2)
    else:
        user.rating = 0.0

    db.session.commit()


def update_user_badge(user):
    completed = user.completed_exchanges or 0
    trust = user.trust_score or 0
    rating = user.rating or 0.0

    if completed >= 20 and trust >= 120 and rating >= 4.5:
        user.badge = 'Legend Mentor'
    elif completed >= 10 and trust >= 90 and rating >= 4.0:
        user.badge = 'Elite Guide'
    elif completed >= 5 and trust >= 70:
        user.badge = 'Trusted Mentor'
    elif completed >= 2:
        user.badge = 'Active Learner'
    else:
        user.badge = 'New Explorer'


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('Admin access only.', 'danger')
        return False
    return True


def contains_skill(skill_text, search_term):
    if not skill_text or not search_term:
        return False
    return search_term.lower() in skill_text.lower()


def get_notification_counts():
    unread_messages = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    pending_sessions = SessionBooking.query.filter_by(receiver_id=current_user.id, status='Pending').count()
    favorite_count = Favorite.query.filter_by(user_id=current_user.id).count()
    return unread_messages, pending_sessions, favorite_count


def is_favorite(user_id, target_user_id):
    return Favorite.query.filter_by(user_id=user_id, favorite_user_id=target_user_id).first() is not None


def refresh_all_user_badges():
    users = User.query.all()
    for user in users:
        update_user_badge(user)
    db.session.commit()


def calculate_match_score(current_user_obj, other_user):
    score = 0
    reasons = []

    current_offered = convert_skills_to_set(current_user_obj.skills_offered)
    current_wanted = convert_skills_to_set(current_user_obj.skills_wanted)

    other_offered = convert_skills_to_set(other_user.skills_offered)
    other_wanted = convert_skills_to_set(other_user.skills_wanted)

    they_can_teach_me = current_wanted.intersection(other_offered)
    i_can_teach_them = current_offered.intersection(other_wanted)

    if they_can_teach_me:
        score += len(they_can_teach_me) * 30
        reasons.append(f"They can teach you: {', '.join(sorted(they_can_teach_me))}")

    if i_can_teach_them:
        score += len(i_can_teach_them) * 25
        reasons.append(f"You can teach them: {', '.join(sorted(i_can_teach_them))}")

    score += int((other_user.rating or 0) * 10)
    if (other_user.rating or 0) >= 4:
        reasons.append("High user rating")

    score += int((other_user.trust_score or 0) / 5)
    if (other_user.trust_score or 0) >= 70:
        reasons.append("Trusted user")

    score += (other_user.completed_exchanges or 0) * 2
    if (other_user.completed_exchanges or 0) >= 5:
        reasons.append("Experienced in skill exchanges")

    return score, reasons, they_can_teach_me, i_can_teach_them


def get_chat_room(user1_id, user2_id):
    smaller = min(user1_id, user2_id)
    larger = max(user1_id, user2_id)
    return f"chat_{smaller}_{larger}"


app.jinja_env.globals.update(is_favorite=is_favorite)

# ------------------ Gemini AI Helpers ------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def ensure_gemini_client():
    if not gemini_client:
        raise ValueError("GEMINI_API_KEY is missing. Please set it in environment variables.")


QUIZ_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "option1": {"type": "string"},
                    "option2": {"type": "string"},
                    "option3": {"type": "string"},
                    "option4": {"type": "string"},
                    "correct_answer": {"type": "string"}
                },
                "required": [
                    "question",
                    "option1",
                    "option2",
                    "option3",
                    "option4",
                    "correct_answer"
                ]
            }
        }
    },
    "required": ["skill", "questions"]
}

def generate_quiz_with_gemini(skill: str, num_questions: int = 5) -> dict:
    ensure_gemini_client()

    prompt = f"""
You are an expert trainer.

Generate {num_questions} HIGH QUALITY MCQ questions for learning {skill}.

Rules:
- Questions must be practical and interview-level
- Include beginner + intermediate mix
- Each question must have 4 options
- Only ONE correct answer
- Avoid vague questions
- Keep options realistic

Return JSON only:
skill, questions[]
"""

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QUIZ_RESPONSE_SCHEMA
        )
    )

    return json.loads(response.text)

# ------------------ Routes ------------------

@app.route('/')
def index():
    refresh_all_user_badges()

    total_users = User.query.count()
    total_sessions = SessionBooking.query.count()
    total_reviews = Review.query.count()
    total_posts = SkillPost.query.count()

    return render_template(
        'index.html',
        total_users=total_users,
        total_sessions=total_sessions,
        total_reviews=total_reviews,
        total_posts=total_posts
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        anonymous_name = request.form['anonymous_name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']

        existing_user = User.query.filter(
            (User.email == email) | (User.anonymous_name == anonymous_name)
        ).first()

        if existing_user:
            flash('Anonymous name or email already exists.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        new_user = User(
            anonymous_name=anonymous_name,
            email=email,
            password=hashed_password
        )

        update_user_badge(new_user)

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    update_user_badge(current_user)
    db.session.commit()

    sent_count = SessionBooking.query.filter_by(sender_id=current_user.id).count()
    received_count = SessionBooking.query.filter_by(receiver_id=current_user.id).count()
    review_count = Review.query.filter_by(reviewee_id=current_user.id).count()
    unread_count, pending_session_count, favorite_count = get_notification_counts()
    post_count = SkillPost.query.filter_by(user_id=current_user.id).count()
    certificate_count = Certificate.query.filter_by(user_id=current_user.id).count()
    completed_count = SessionBooking.query.filter(
        ((SessionBooking.sender_id == current_user.id) | (SessionBooking.receiver_id == current_user.id)) &
        (SessionBooking.status == 'Completed')
    ).count()

    return render_template(
        'dashboard.html',
        user=current_user,
        sent_count=sent_count,
        received_count=received_count,
        review_count=review_count,
        completed_count=completed_count,
        unread_count=unread_count,
        pending_session_count=pending_session_count,
        favorite_count=favorite_count,
        post_count=post_count,
        certificate_count=certificate_count
    )


@app.route('/leaderboard')
@login_required
def leaderboard():
    refresh_all_user_badges()

    top_rated_users = User.query.order_by(User.rating.desc(), User.trust_score.desc()).limit(10).all()
    top_trusted_users = User.query.order_by(User.trust_score.desc(), User.rating.desc()).limit(10).all()
    most_active_users = User.query.order_by(User.completed_exchanges.desc(), User.trust_score.desc()).limit(10).all()

    return render_template(
        'leaderboard.html',
        top_rated_users=top_rated_users,
        top_trusted_users=top_trusted_users,
        most_active_users=most_active_users
    )


@app.route('/recommendations')
@login_required
def recommendations():
    recommended_users = []

    all_users = User.query.filter(User.id != current_user.id).all()

    for user in all_users:
        score, reasons, they_can_teach_me, i_can_teach_them = calculate_match_score(current_user, user)

        if score > 0:
            update_user_badge(user)
            recommended_users.append({
                'user': user,
                'score': score,
                'reasons': reasons,
                'they_can_teach_me': sorted(list(they_can_teach_me)),
                'i_can_teach_them': sorted(list(i_can_teach_them)),
                'is_favorite': is_favorite(current_user.id, user.id)
            })

    db.session.commit()

    recommended_users.sort(key=lambda item: item['score'], reverse=True)

    return render_template('recommendations.html', recommended_users=recommended_users)


@app.route('/skill-search')
@login_required
def skill_search():
    query = request.args.get('query', '').strip()
    users = []

    if query:
        users = User.query.filter(
            User.id != current_user.id,
            (
                User.skills_offered.ilike(f"%{query}%") |
                User.skills_wanted.ilike(f"%{query}%")
            )
        ).all()

        for user in users:
            update_user_badge(user)
        db.session.commit()

    return render_template('skill_search.html', users=users, query=query)


@app.route('/certificates')
@login_required
def certificates():
    user_certs = Certificate.query.filter_by(user_id=current_user.id).order_by(Certificate.issue_date.desc()).all()
    return render_template('certificates.html', certificates=user_certs)


@app.route('/certificate/<int:cert_id>')
@login_required
def view_certificate(cert_id):
    cert = Certificate.query.get_or_404(cert_id)

    if cert.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('certificates'))

    return render_template('view_certificate.html', cert=cert)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    avatar_choices = ['🧠', '🚀', '🎯', '💡', '📚', '🛡️', '🎨', '💻', '🌟', '🔥']

    if request.method == 'POST':
        current_user.skills_offered = request.form['skills_offered']
        current_user.skills_wanted = request.form['skills_wanted']
        current_user.bio = request.form['bio'].strip()
        selected_avatar = request.form.get('avatar', '🧠')

        if selected_avatar in avatar_choices:
            current_user.avatar = selected_avatar

        update_user_badge(current_user)
        db.session.commit()

        flash('Profile updated successfully.', 'success')
        return redirect(url_for('dashboard'))

    user_reviews = Review.query.filter_by(reviewee_id=current_user.id).order_by(Review.created_at.desc()).all()
    return render_template('profile.html', user=current_user, user_reviews=user_reviews, avatar_choices=avatar_choices)


@app.route('/matches')
@login_required
def matches():
    search_skill = request.args.get('skill', '').strip()
    min_rating = request.args.get('min_rating', '').strip()
    min_trust = request.args.get('min_trust', '').strip()

    current_user_offered = convert_skills_to_set(current_user.skills_offered)
    current_user_wanted = convert_skills_to_set(current_user.skills_wanted)

    matched_users = []
    all_users = User.query.filter(User.id != current_user.id).all()

    for user in all_users:
        other_offered = convert_skills_to_set(user.skills_offered)
        other_wanted = convert_skills_to_set(user.skills_wanted)

        they_can_teach_me = current_user_wanted.intersection(other_offered)
        i_can_teach_them = current_user_offered.intersection(other_wanted)

        if not (they_can_teach_me and i_can_teach_them):
            continue

        if search_skill:
            skill_match_found = (
                contains_skill(user.skills_offered, search_skill) or
                contains_skill(user.skills_wanted, search_skill)
            )
            if not skill_match_found:
                continue

        if min_rating:
            try:
                if user.rating < float(min_rating):
                    continue
            except ValueError:
                pass

        if min_trust:
            try:
                if user.trust_score < int(min_trust):
                    continue
            except ValueError:
                pass

        update_user_badge(user)

        matched_users.append({
            'user': user,
            'they_can_teach_me': sorted(list(they_can_teach_me)),
            'i_can_teach_them': sorted(list(i_can_teach_them)),
            'is_favorite': is_favorite(current_user.id, user.id)
        })

    db.session.commit()

    matched_users.sort(key=lambda item: (-item['user'].rating, -item['user'].trust_score))

    return render_template(
        'matches.html',
        matched_users=matched_users,
        search_skill=search_skill,
        min_rating=min_rating,
        min_trust=min_trust
    )


@app.route('/board')
@login_required
def board():
    filter_type = request.args.get('type', '').strip()
    search_skill = request.args.get('skill', '').strip()

    posts_query = SkillPost.query.filter_by(status='Open')

    if filter_type in ['Learn', 'Teach']:
        posts_query = posts_query.filter_by(post_type=filter_type)

    if search_skill:
        posts_query = posts_query.filter(SkillPost.skill_name.ilike(f"%{search_skill}%"))

    posts = posts_query.order_by(SkillPost.created_at.desc()).all()

    return render_template(
        'board.html',
        posts=posts,
        filter_type=filter_type,
        search_skill=search_skill
    )


@app.route('/create-post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form['post_type'].strip()
        skill_name = request.form['skill_name'].strip()
        description = request.form['description'].strip()
        availability = request.form['availability'].strip()

        if post_type not in ['Learn', 'Teach']:
            flash('Invalid post type.', 'danger')
            return redirect(url_for('create_post'))

        if not skill_name or not description:
            flash('Skill name and description are required.', 'danger')
            return redirect(url_for('create_post'))

        new_post = SkillPost(
            user_id=current_user.id,
            post_type=post_type,
            skill_name=skill_name,
            description=description,
            availability=availability
        )

        db.session.add(new_post)
        db.session.commit()

        flash('Skill post created successfully.', 'success')
        return redirect(url_for('my_posts'))

    return render_template('create_post.html')


@app.route('/edit-post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = SkillPost.query.get_or_404(post_id)

    if post.user_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_posts'))

    if request.method == 'POST':
        post_type = request.form['post_type'].strip()
        skill_name = request.form['skill_name'].strip()
        description = request.form['description'].strip()
        availability = request.form['availability'].strip()
        status = request.form['status'].strip()

        if post_type not in ['Learn', 'Teach']:
            flash('Invalid post type.', 'danger')
            return redirect(url_for('edit_post', post_id=post.id))

        if status not in ['Open', 'Closed']:
            flash('Invalid status.', 'danger')
            return redirect(url_for('edit_post', post_id=post.id))

        if not skill_name or not description:
            flash('Skill name and description are required.', 'danger')
            return redirect(url_for('edit_post', post_id=post.id))

        post.post_type = post_type
        post.skill_name = skill_name
        post.description = description
        post.availability = availability
        post.status = status

        db.session.commit()

        flash('Post updated successfully.', 'success')
        return redirect(url_for('my_posts'))

    return render_template('edit_post.html', post=post)


@app.route('/my-posts')
@login_required
def my_posts():
    posts = SkillPost.query.filter_by(user_id=current_user.id).order_by(SkillPost.created_at.desc()).all()
    return render_template('my_posts.html', posts=posts)


@app.route('/close-post/<int:post_id>')
@login_required
def close_post(post_id):
    post = SkillPost.query.get_or_404(post_id)

    if post.user_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_posts'))

    post.status = 'Closed'
    db.session.commit()

    flash('Post closed successfully.', 'info')
    return redirect(url_for('my_posts'))


@app.route('/delete-post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = SkillPost.query.get_or_404(post_id)

    if post.user_id != current_user.id and not current_user.is_admin:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_posts'))

    db.session.delete(post)
    db.session.commit()

    flash('Post deleted successfully.', 'success')
    return redirect(url_for('my_posts'))


@app.route('/favorites')
@login_required
def favorites():
    favorite_records = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
    return render_template('favorites.html', favorite_records=favorite_records)


@app.route('/add-favorite/<int:user_id>')
@login_required
def add_favorite(user_id):
    target_user = User.query.get_or_404(user_id)

    if target_user.id == current_user.id:
        flash('You cannot favorite yourself.', 'warning')
        return redirect(url_for('matches'))

    existing_favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        favorite_user_id=target_user.id
    ).first()

    if existing_favorite:
        flash('User already in favorites.', 'info')
        return redirect(request.referrer or url_for('matches'))

    new_favorite = Favorite(
        user_id=current_user.id,
        favorite_user_id=target_user.id
    )

    db.session.add(new_favorite)
    db.session.commit()

    flash('User added to favorites.', 'success')
    return redirect(request.referrer or url_for('matches'))


@app.route('/remove-favorite/<int:user_id>')
@login_required
def remove_favorite(user_id):
    favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        favorite_user_id=user_id
    ).first()

    if not favorite:
        flash('Favorite not found.', 'warning')
        return redirect(request.referrer or url_for('favorites'))

    db.session.delete(favorite)
    db.session.commit()

    flash('User removed from favorites.', 'info')
    return redirect(request.referrer or url_for('favorites'))


@app.route('/book-session/<int:user_id>', methods=['GET', 'POST'])
@login_required
def book_session(user_id):
    receiver = User.query.get_or_404(user_id)

    if receiver.id == current_user.id:
        flash('You cannot book a session with yourself.', 'danger')
        return redirect(url_for('matches'))

    if request.method == 'POST':
        topic = request.form['topic']
        session_date = request.form['session_date']
        session_time = request.form['session_time']
        message = request.form['message']

        new_booking = SessionBooking(
            sender_id=current_user.id,
            receiver_id=receiver.id,
            topic=topic,
            session_date=session_date,
            session_time=session_time,
            message=message
        )

        db.session.add(new_booking)
        db.session.commit()

        flash('Session booking request sent successfully.', 'success')
        return redirect(url_for('my_sessions'))

    return render_template('book_session.html', receiver=receiver)


@app.route('/my-sessions')
@login_required
def my_sessions():
    sent_sessions = SessionBooking.query.filter_by(sender_id=current_user.id).order_by(SessionBooking.created_at.desc()).all()
    received_sessions = SessionBooking.query.filter_by(receiver_id=current_user.id).order_by(SessionBooking.created_at.desc()).all()

    return render_template(
        'my_sessions.html',
        sent_sessions=sent_sessions,
        received_sessions=received_sessions
    )


@app.route('/update-session-status/<int:session_id>/<string:new_status>')
@login_required
def update_session_status(session_id, new_status):
    session = SessionBooking.query.get_or_404(session_id)

    if session.receiver_id != current_user.id and session.sender_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_sessions'))

    allowed_status = ['Accepted', 'Rejected', 'Completed']

    if new_status not in allowed_status:
        flash('Invalid status update.', 'danger')
        return redirect(url_for('my_sessions'))

    if new_status in ['Accepted', 'Rejected'] and session.receiver_id != current_user.id:
        flash('Only the receiver can accept or reject requests.', 'warning')
        return redirect(url_for('my_sessions'))

    if new_status == 'Completed':
        if session.status != 'Accepted':
            flash('Only accepted sessions can be marked completed.', 'warning')
            return redirect(url_for('my_sessions'))

        session.status = 'Completed'
        session.sender.completed_exchanges = (session.sender.completed_exchanges or 0) + 1
        session.receiver.completed_exchanges = (session.receiver.completed_exchanges or 0) + 1
        session.sender.trust_score += 5
        session.receiver.trust_score += 5

        cert1 = Certificate(
            user_id=session.sender.id,
            partner_id=session.receiver.id,
            session_id=session.id,
            skill=session.topic
        )

        cert2 = Certificate(
            user_id=session.receiver.id,
            partner_id=session.sender.id,
            session_id=session.id,
            skill=session.topic
        )

        db.session.add(cert1)
        db.session.add(cert2)

        update_user_badge(session.sender)
        update_user_badge(session.receiver)

        db.session.commit()
        flash('Session completed! Certificates generated 🎉', 'success')
        return redirect(url_for('my_sessions'))

    session.status = new_status
    db.session.commit()
    flash(f'Session {new_status.lower()} successfully.', 'success')
    return redirect(url_for('my_sessions'))


@app.route('/give-review/<int:session_id>/<int:reviewee_id>', methods=['GET', 'POST'])
@login_required
def give_review(session_id, reviewee_id):
    session = SessionBooking.query.get_or_404(session_id)
    reviewee = User.query.get_or_404(reviewee_id)

    if current_user.id not in [session.sender_id, session.receiver_id]:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('my_sessions'))

    if reviewee_id not in [session.sender_id, session.receiver_id]:
        flash('Invalid review target.', 'danger')
        return redirect(url_for('my_sessions'))

    if reviewee_id == current_user.id:
        flash('You cannot review yourself.', 'warning')
        return redirect(url_for('my_sessions'))

    if session.status != 'Completed':
        flash('You can only review after session completion.', 'warning')
        return redirect(url_for('my_sessions'))

    existing_review = Review.query.filter_by(
        session_id=session.id,
        reviewer_id=current_user.id
    ).first()

    if existing_review:
        flash('You already submitted a review for this session.', 'info')
        return redirect(url_for('my_sessions'))

    if request.method == 'POST':
        stars = int(request.form['stars'])
        feedback = request.form['feedback']

        if stars < 1 or stars > 5:
            flash('Rating must be between 1 and 5.', 'danger')
            return redirect(url_for('give_review', session_id=session.id, reviewee_id=reviewee_id))

        new_review = Review(
            session_id=session.id,
            reviewer_id=current_user.id,
            reviewee_id=reviewee_id,
            stars=stars,
            feedback=feedback
        )

        db.session.add(new_review)
        db.session.commit()

        update_user_rating(reviewee_id)
        update_user_badge(reviewee)
        db.session.commit()

        flash('Review submitted successfully.', 'success')
        return redirect(url_for('my_sessions'))

    return render_template('give_review.html', session=session, reviewee=reviewee)


@app.route('/user/<int:user_id>')
@login_required
def view_user(user_id):
    user = User.query.get_or_404(user_id)
    update_user_badge(user)
    db.session.commit()

    user_reviews = Review.query.filter_by(reviewee_id=user.id).order_by(Review.created_at.desc()).all()
    favorite_status = is_favorite(current_user.id, user.id) if current_user.is_authenticated else False
    return render_template('view_user.html', user=user, user_reviews=user_reviews, favorite_status=favorite_status)


# ------------------ Messaging Routes ------------------

@app.route('/send-message/<int:user_id>', methods=['GET', 'POST'])
@login_required
def send_message(user_id):
    receiver = User.query.get_or_404(user_id)

    if receiver.id == current_user.id:
        flash('You cannot send a message to yourself.', 'warning')
        return redirect(url_for('matches'))

    if request.method == 'POST':
        subject = request.form['subject'].strip()
        body = request.form['body'].strip()

        if not subject or not body:
            flash('Subject and message body are required.', 'danger')
            return redirect(url_for('send_message', user_id=user_id))

        new_message = Message(
            sender_id=current_user.id,
            receiver_id=receiver.id,
            subject=subject,
            body=body
        )

        db.session.add(new_message)
        db.session.commit()

        flash('Message sent successfully.', 'success')
        return redirect(url_for('inbox'))

    return render_template('send_message.html', receiver=receiver)


@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    other_user = User.query.get_or_404(user_id)

    if other_user.id == current_user.id:
        flash('You cannot chat with yourself.', 'warning')
        return redirect(url_for('dashboard'))

    room = get_chat_room(current_user.id, other_user.id)

    messages = Message.query.filter(
        (
            (Message.sender_id == current_user.id) &
            (Message.receiver_id == other_user.id)
        ) |
        (
            (Message.sender_id == other_user.id) &
            (Message.receiver_id == current_user.id)
        )
    ).order_by(Message.created_at.asc()).all()

    return render_template(
        'chat.html',
        other_user=other_user,
        room=room,
        messages=messages
    )

@app.route('/delete_chat/<int:user_id>')
@login_required
def delete_chat(user_id):
    other_user = User.query.get_or_404(user_id)

    if other_user.id == current_user.id:
        flash('You cannot delete chat with yourself.', 'warning')
        return redirect(url_for('dashboard'))

    Message.query.filter(
        (
            (Message.sender_id == current_user.id) &
            (Message.receiver_id == other_user.id)
        ) |
        (
            (Message.sender_id == other_user.id) &
            (Message.receiver_id == current_user.id)
        )
    ).delete(synchronize_session=False)

    db.session.commit()

    flash('Entire chat deleted successfully.', 'success')
    return redirect(url_for('chat', user_id=other_user.id))

@app.route('/delete_message/<int:message_id>')
@login_required
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)

    # Only sender can delete their message
    if message.sender_id != current_user.id:
        flash("You can't delete this message.", "danger")
        return redirect(url_for('dashboard'))

    chat_user_id = message.receiver_id

    db.session.delete(message)
    db.session.commit()

    flash("Message deleted successfully.", "success")
    return redirect(url_for('chat', user_id=chat_user_id))

@app.route('/inbox')
@login_required
def inbox():
    received_messages = Message.query.filter_by(
        receiver_id=current_user.id,
        parent_id=None
    ).order_by(Message.created_at.desc()).all()

    sent_messages = Message.query.filter_by(
        sender_id=current_user.id,
        parent_id=None
    ).order_by(Message.created_at.desc()).all()

    return render_template(
        'inbox.html',
        received_messages=received_messages,
        sent_messages=sent_messages
    )


@app.route('/message/<int:message_id>', methods=['GET', 'POST'])
@login_required
def view_message(message_id):
    message = Message.query.get_or_404(message_id)

    if current_user.id not in [message.sender_id, message.receiver_id]:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('inbox'))

    if current_user.id == message.receiver_id and not message.is_read:
        message.is_read = True
        db.session.commit()

    if request.method == 'POST':
        reply_body = request.form['reply_body'].strip()

        if not reply_body:
            flash('Reply cannot be empty.', 'danger')
            return redirect(url_for('view_message', message_id=message.id))

        other_user_id = message.sender_id if current_user.id == message.receiver_id else message.receiver_id

        reply_message = Message(
            sender_id=current_user.id,
            receiver_id=other_user_id,
            subject=f"Re: {message.subject}",
            body=reply_body,
            parent_id=message.id if message.parent_id is None else message.parent_id
        )

        db.session.add(reply_message)
        db.session.commit()

        flash('Reply sent successfully.', 'success')
        return redirect(url_for('view_message', message_id=message.id))

    root_message = message if message.parent_id is None else Message.query.get(message.parent_id)
    conversation_messages = Message.query.filter(
        (Message.id == root_message.id) | (Message.parent_id == root_message.id)
    ).order_by(Message.created_at.asc()).all()

    for msg in conversation_messages:
        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True

    db.session.commit()

    return render_template(
        'view_message.html',
        message=message,
        root_message=root_message,
        conversation_messages=conversation_messages
    )


# ------------------ Socket Events ------------------

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)


@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return

    room = data.get('room')
    receiver_id = data.get('receiver_id')
    body = (data.get('body') or '').strip()

    if not room or not receiver_id or not body:
        return

    try:
        receiver_id = int(receiver_id)
    except ValueError:
        return

    if receiver_id == current_user.id:
        return

    new_message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        subject='Live Chat',
        body=body,
        is_read=False
    )

    db.session.add(new_message)
    db.session.commit()

    emit('receive_message', {
        'sender_id': current_user.id,
        'sender_name': current_user.anonymous_name,
        'body': body,
        'created_at': new_message.created_at.strftime('%d %b %Y, %I:%M %p')
    }, room=room)

# ------------------ Voice Call Socket Events ------------------

@socketio.on('call_user')
def handle_call_user(data):
    if not current_user.is_authenticated:
        return

    room = data.get('room')
    offer = data.get('offer')
    target_user_id = data.get('target_user_id')

    if not room or not offer or not target_user_id:
        return

    emit('incoming_call', {
        'caller_id': current_user.id,
        'caller_name': current_user.anonymous_name,
        'offer': offer
    }, room=room)


@socketio.on('answer_call')
def handle_answer_call(data):
    if not current_user.is_authenticated:
        return

    room = data.get('room')
    answer = data.get('answer')

    if not room or not answer:
        return

    emit('call_answered', {
        'answer': answer,
        'answerer_id': current_user.id,
        'answerer_name': current_user.anonymous_name
    }, room=room)


@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    if not current_user.is_authenticated:
        return

    room = data.get('room')
    candidate = data.get('candidate')

    if not room or not candidate:
        return

    emit('ice_candidate', {
        'candidate': candidate,
        'sender_id': current_user.id
    }, room=room)


@socketio.on('end_call')
def handle_end_call(data):
    if not current_user.is_authenticated:
        return

    room = data.get('room')
    if not room:
        return

    emit('call_ended', {
        'ended_by': current_user.anonymous_name
    }, room=room)

# ------------------ AI Learning Routes ------------------

@app.route('/learning')
@login_required
def learning_home():
    quiz_skills = db.session.query(Quiz.skill).distinct().all()
    skills = sorted(set([s[0] for s in quiz_skills]))
    return render_template('learning_home.html', skills=skills)

@app.route('/generate-quiz/<skill>')
@login_required
def generate_quiz(skill):
    try:
        data = generate_quiz_with_gemini(skill=skill, num_questions=5)

        created_count = 0
        for item in data.get("questions", []):
            quiz = Quiz(
                skill=skill,
                question=item["question"],
                option1=item["option1"],
                option2=item["option2"],
                option3=item["option3"],
                option4=item["option4"],
                correct_answer=item["correct_answer"],
                source='AI'
            )
            db.session.add(quiz)
            created_count += 1

        db.session.commit()
        flash(f'{created_count} AI quiz questions generated for {skill}.', 'success')
    except Exception as e:
        flash(f'Failed to generate quiz: {str(e)}', 'danger')

    return redirect(url_for('quiz', skill=skill))

@app.route('/quiz/<skill>', methods=['GET', 'POST'])
@login_required
def quiz(skill):
    questions = Quiz.query.filter_by(skill=skill).order_by(Quiz.created_at.desc()).limit(10).all()

    if request.method == 'POST':
        if not questions:
            flash(f'No quiz available yet for {skill}.', 'warning')
            return redirect(url_for('learning_home'))

        score = 0

        for q in questions:
            selected = request.form.get(str(q.id))
            if selected == q.correct_answer:
                score += 1

        total_questions = len(questions)

        result = QuizResult(
            user_id=current_user.id,
            skill=skill,
            score=score,
            total_questions=total_questions
        )
        db.session.add(result)

        existing_certificate = LearningCertificate.query.filter_by(
            user_id=current_user.id,
            skill=skill
        ).first()

        if score >= int(total_questions * 0.6) and not existing_certificate:
            cert = LearningCertificate(
                user_id=current_user.id,
                skill=skill,
                score=score,
                total_questions=total_questions
            )
            db.session.add(cert)

        db.session.commit()

        if score >= int(total_questions * 0.6):
            flash(f'You scored {score}/{total_questions}. Certificate earned! 🎉', 'success')
        else:
            flash(f'You scored {score}/{total_questions}. Score 60%+ to earn certificate.', 'info')

        return redirect(url_for('quiz_results'))

    return render_template('quiz.html', questions=questions, skill=skill)

@app.route('/quiz-results')
@login_required
def quiz_results():
    results = QuizResult.query.filter_by(user_id=current_user.id).order_by(QuizResult.created_at.desc()).all()
    return render_template('quiz_results.html', results=results)


@app.route('/learning-certificates')
@login_required
def learning_certificates():
    certificates = LearningCertificate.query.filter_by(user_id=current_user.id).order_by(LearningCertificate.date_earned.desc()).all()
    return render_template('learning_certificates.html', certificates=certificates)


@app.route('/learning-certificate/<int:certificate_id>')
@login_required
def view_learning_certificate(certificate_id):
    certificate = LearningCertificate.query.get_or_404(certificate_id)

    if certificate.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('learning_certificates'))

    return render_template('view_learning_certificate.html', certificate=certificate)

# ------------------ Admin Routes ------------------

@app.route('/admin')
@login_required
def admin_dashboard():
    if not admin_required():
        return redirect(url_for('dashboard'))

    refresh_all_user_badges()

    total_users = User.query.count()
    total_sessions = SessionBooking.query.count()
    total_reviews = Review.query.count()
    total_posts = SkillPost.query.count()
    total_certificates = Certificate.query.count()

    users = User.query.order_by(User.id.desc()).all()
    sessions = SessionBooking.query.order_by(SessionBooking.created_at.desc()).all()
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    posts = SkillPost.query.order_by(SkillPost.created_at.desc()).all()
    certificates = Certificate.query.order_by(Certificate.issue_date.desc()).all()

    pending_sessions = SessionBooking.query.filter_by(status='Pending').count()
    accepted_sessions = SessionBooking.query.filter_by(status='Accepted').count()
    rejected_sessions = SessionBooking.query.filter_by(status='Rejected').count()
    completed_sessions = SessionBooking.query.filter_by(status='Completed').count()

    learn_posts = SkillPost.query.filter_by(post_type='Learn').count()
    teach_posts = SkillPost.query.filter_by(post_type='Teach').count()

    star_1 = Review.query.filter_by(stars=1).count()
    star_2 = Review.query.filter_by(stars=2).count()
    star_3 = Review.query.filter_by(stars=3).count()
    star_4 = Review.query.filter_by(stars=4).count()
    star_5 = Review.query.filter_by(stars=5).count()

    return render_template(
        'admin.html',
        total_users=total_users,
        total_sessions=total_sessions,
        total_reviews=total_reviews,
        total_posts=total_posts,
        total_certificates=total_certificates,
        users=users,
        sessions=sessions,
        reviews=reviews,
        posts=posts,
        certificates=certificates,
        pending_sessions=pending_sessions,
        accepted_sessions=accepted_sessions,
        rejected_sessions=rejected_sessions,
        completed_sessions=completed_sessions,
        learn_posts=learn_posts,
        teach_posts=teach_posts,
        star_1=star_1,
        star_2=star_2,
        star_3=star_3,
        star_4=star_4,
        star_5=star_5
    )


@app.route('/make-admin/<int:user_id>')
@login_required
def make_admin(user_id):
    if not admin_required():
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()

    flash(f'{user.anonymous_name} is now an admin.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/remove-admin/<int:user_id>')
@login_required
def remove_admin(user_id):
    if not admin_required():
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot remove your own admin access.', 'warning')
        return redirect(url_for('admin_dashboard'))

    user.is_admin = False
    db.session.commit()

    flash(f'Admin access removed from {user.anonymous_name}.', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/delete-user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not admin_required():
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account from admin panel.', 'warning')
        return redirect(url_for('admin_dashboard'))

    Favorite.query.filter(
        (Favorite.user_id == user.id) | (Favorite.favorite_user_id == user.id)
    ).delete(synchronize_session=False)

    SkillPost.query.filter_by(user_id=user.id).delete(synchronize_session=False)

    Message.query.filter(
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    ).delete(synchronize_session=False)

    Review.query.filter(
        (Review.reviewer_id == user.id) | (Review.reviewee_id == user.id)
    ).delete(synchronize_session=False)

    Certificate.query.filter(
        (Certificate.user_id == user.id) | (Certificate.partner_id == user.id)
    ).delete(synchronize_session=False)

    SessionBooking.query.filter(
        (SessionBooking.sender_id == user.id) | (SessionBooking.receiver_id == user.id)
    ).delete(synchronize_session=False)

    db.session.delete(user)
    db.session.commit()

    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        admin_email = 'admin@skillsphere.com'
        existing_admin = User.query.filter_by(email=admin_email).first()
        
        if not existing_admin:
            admin_user = User(
                anonymous_name='AdminMaster',
                email=admin_email,
                password=generate_password_hash('admin123'),
                is_admin=True,
                skills_offered='Management, Monitoring',
                skills_wanted='',
                trust_score=100,
                avatar='🛡️',
                bio='Official platform administrator.',
                badge='Legend Mentor'
            )
            db.session.add(admin_user)
            db.session.commit()
        if not Quiz.query.first():
            sample_quizzes = [
                Quiz(
                    skill='Python',
                    question='Which of the following is a mutable data type in Python?',
                    option1='Tuple',
                    option2='String',
                    option3='List',
                    option4='Integer',
                    correct_answer='List'
                ),
                Quiz(
                    skill='Python',
                    question='Which keyword is used to define a function in Python?',
                    option1='function',
                    option2='def',
                    option3='fun',
                    option4='define',
                    correct_answer='def'
                ),
                Quiz(
                    skill='Python',
                    question='What is the output type of input() in Python?',
                    option1='int',
                    option2='float',
                    option3='string',
                    option4='list',
                    correct_answer='string'
                ),
                Quiz(
                    skill='SQL',
                    question='Which SQL statement is used to retrieve data?',
                    option1='GET',
                    option2='FETCH',
                    option3='SELECT',
                    option4='SHOW',
                    correct_answer='SELECT'
                ),
                Quiz(
                    skill='SQL',
                    question='Which clause is used to filter records?',
                    option1='ORDER BY',
                    option2='WHERE',
                    option3='GROUP BY',
                    option4='SORT',
                    correct_answer='WHERE'
                ),
                Quiz(
                    skill='Excel',
                    question='Which symbol is used to start a formula in Excel?',
                    option1='#',
                    option2='@',
                    option3='=',
                    option4='&',
                    correct_answer='='
                ),
                Quiz(
                    skill='Excel',
                    question='Which Excel function is used to calculate average?',
                    option1='SUM()',
                    option2='AVERAGE()',
                    option3='COUNT()',
                    option4='MEAN()',
                    correct_answer='AVERAGE()'
                )
            ]

            db.session.add_all(sample_quizzes)
            db.session.commit()
    socketio.run(app, debug=True)