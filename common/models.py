import enum, pdb, re, threading, time, datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, UUID4
from dateutil import tz
from uuid import uuid4
import logging
logger = logging.getLogger(__name__)

from common.database import Base, SessLocal, fa_users_db
from common.utils import vars, utcnow, nowtz

from sqlalchemy import text, Column, Integer, Enum, Float, ForeignKey, Boolean, JSON, Date, Unicode, \
    func, TIMESTAMP, select, or_, and_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, backref, object_session, column_property
from sqlalchemy.dialects.postgresql import UUID, BYTEA, JSONB, ARRAY
from sqlalchemy_utils.types import EmailType
from sqlalchemy_utils.types.encrypted.encrypted_type import StringEncryptedType, FernetEngine


from fastapi_sqlalchemy import db  # an object to provide global access to a database session
from fastapi_users import models as fu_models
from fastapi_users.db import SQLAlchemyBaseUserTable, SQLAlchemyUserDatabase


# Schemas naming convention: SOModel for "schema out model", SIModel for "schema in"
class SOut(BaseModel):
    class Config:
        orm_mode = True


# https://dev.to/zchtodd/sqlalchemy-cascading-deletes-8hk
parent_cascade = dict(cascade="all, delete", passive_deletes=True)
child_cascade = dict(ondelete="cascade")

# Note: using sa.Unicode for all Text/Varchar columns to be consistent with sqlalchemy_utils examples. Also keeping all
# text fields unlimited (no varchar(max_length)) as Postgres doesn't incur penalty, unlike MySQL, and we don't know
# how long str will be after encryption.
def Encrypt(Col=Unicode, array=False, **args):
    enc = StringEncryptedType(Col, vars.FLASK_KEY, FernetEngine)
    if array: enc = ARRAY(enc)
    return Column(enc, **args)

# TODO should all date-cols be index=True? (eg sorting, filtering)
def DateCol(default=True, update=False):
    args = {}
    if default: args['default'] = datetime.datetime.utcnow
    if update: args['onupdate'] = datetime.datetime.utcnow
    return Column(TIMESTAMP(timezone=True), index=True, **args)

def IDCol():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

def FKCol(fk, **kwargs):
    return Column(UUID(as_uuid=True), ForeignKey(fk, **child_cascade), **kwargs)



class User(Base, SQLAlchemyBaseUserTable):
    __tablename__ = 'users'

    created_at = DateCol()
    updated_at = DateCol(update=True)

    first_name = Encrypt()
    last_name = Encrypt()
    gender = Encrypt()
    orientation = Encrypt()
    birthday = Column(Date)  # TODO encrypt (how to store/migrate dates?)
    timezone = Column(Unicode)
    bio = Encrypt()
    is_cool = Column(Boolean, default=False)

    habitica_user_id = Encrypt()
    habitica_api_token = Encrypt()

    entries = relationship("Entry", order_by='Entry.created_at.desc()', **parent_cascade)
    field_entries = relationship("FieldEntry", order_by='FieldEntry.created_at.desc()', **parent_cascade)
    fields = relationship("Field", order_by='Field.created_at.asc()', **parent_cascade)
    people = relationship("Person", order_by='Person.name.asc()', **parent_cascade)
    shares = relationship("Share", **parent_cascade)
    tags = relationship("Tag", order_by='Tag.name.asc()', **parent_cascade)

    @staticmethod
    def snoop(viewer, as_id=None):
        as_user, snooping = None, False
        if as_id and viewer.id != as_id:
            snooping = True
            as_user = db.session.query(User) \
                .join(Share) \
                .filter(Share.email == viewer.email, Share.user_id == as_id) \
                .first()
        if as_user:
            as_user.share_data = db.session.query(Share) \
                .filter_by(user_id=as_id, email=viewer.email) \
                .first()
        else:
            # as_user = viewer
            # fastapi-users giving me beef, re-load from sqlalchemy
            as_user = db.session.query(User).get(viewer.id)
        return as_user, snooping

    @property
    def shared_with_me(self):
        # 9cc44d55: sqlalchemy join. Can't figure out sa select diff cols from join tables
        return db.session.execute("""
        select s.*, u.* from users u
        inner join shares s on s.email=:email and u.id=s.user_id
        """, {'email': self.email}).fetchall()

    def profile_to_text(self):
        txt = ''
        if self.gender:
            txt += f"I am {self.gender}. "
        if self.orientation and not re.match("straight", self.orientation, re.IGNORECASE):
            txt += f"I am {self.orientation}. "
        if self.bio:
            txt += self.bio
        for p in self.people:
            whose = "" if "'" in p.relation.split(' ')[0] else "my "
            txt += f"{p.name} is {whose}{p.relation}. "
            if p.bio: txt += p.bio
            # if p.issues: txt += f" {p.name} has these issues: {p.issues} "
        txt = re.sub(r'\s+', ' ', txt)
        # print(txt)
        return txt


class FU_User(fu_models.BaseUser): pass
class FU_UserCreate(fu_models.BaseUserCreate): pass
class FU_UserUpdate(FU_User, fu_models.BaseUserUpdate): pass
class FU_UserDB(FU_User, fu_models.BaseUserDB): pass
user_db = SQLAlchemyUserDatabase(FU_UserDB, fa_users_db, User.__table__)


class SITimezone(BaseModel):
    timezone: Optional[str] = None


class SIHabitica(BaseModel):
    habitica_user_id: Optional[str] = None
    habitica_api_token: Optional[str] = None


class SIProfile(SITimezone):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    orientation: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[Any] = None
    bio: Optional[str] = None


class SOProfile(SIProfile, SOut):
    pass


class SOSharedWithMe(SOProfile):
    id: UUID4
    email: str
    new_entries: Optional[int]
    # last_seen: Optional[datetime.datetime]


class SOUser(FU_User, fu_models.BaseUserDB):
    timezone: Optional[Any] = None
    habitica_user_id: Optional[str] = None
    habitica_api_token: Optional[str] = None
    is_cool: Optional[bool] = False
    shared_with_me: Optional[List[SOSharedWithMe]]


class Entry(Base):
    __tablename__ = 'entries'

    id = IDCol()
    created_at = DateCol()
    updated_at = DateCol(update=True)

    # Title optional, otherwise generated from text. topic-modeled, or BERT summary, etc?
    title = Encrypt()
    text = Encrypt(Unicode, nullable=False)
    no_ai = Column(Boolean, default=False)
    ai_ran = Column(Boolean, default=False)

    # Generated
    title_summary = Encrypt()
    text_summary = Encrypt()
    sentiment = Encrypt()

    user_id = FKCol('users.id', index=True)
    entry_tags_ = relationship("EntryTag", **parent_cascade)

    # share_tags = relationship("EntryTag", secondary="shares_tags")

    @property
    def entry_tags(self):
        return {t.tag_id: True for t in self.entry_tags_}

    @staticmethod
    def snoop(
        viewer_email: str,
        target_id: str,
        snooping: bool = False,
        entry_id: str = None,
        order_by=None,
        tags: List[str] = None,
        days: int = None,
        for_ai: bool = False
    ):
        if not snooping:
            q = db.session.query(Entry).filter(Entry.user_id == target_id)
        if snooping:
            q = db.session.query(Entry)\
                .join(EntryTag, Entry.id == EntryTag.entry_id)\
                .join(ShareTag, EntryTag.tag_id == ShareTag.tag_id)\
                .join(Share, ShareTag.share_id == Share.id)\
                .filter(Share.email == viewer_email, Share.user_id == target_id)
            # TODO use ORM partial thus far for this query command, not raw sql
            sql = f"""
            update shares set last_seen={utcnow}, new_entries=0
            where email=:email and user_id=:uid
            """
            db.session.execute(text(sql), dict(email=viewer_email, uid=target_id))
            db.session.commit()

        if entry_id:
            q = q.filter(Entry.id == entry_id)

        if for_ai:
            q = q.filter(Entry.no_ai.isnot(True))

        if tags:
            if not snooping:
                # already joined otherwise
                q = q.join(EntryTag, Tag)
            q = q.filter(EntryTag.tag_id.in_(tags))

        if days:
            now = datetime.datetime.utcnow()
            x_days = now - datetime.timedelta(days=days)
            # build a beginning-to-end story
            q = q.filter(Entry.created_at > x_days)
            order_by = Entry.created_at.asc()

        if order_by is None:
            order_by = Entry.created_at.desc()
        return q.order_by(order_by)

    def run_models(self):
        self.ai_ran = False
        if self.no_ai:
            self.title_summary = self.text_summary = self.sentiment = None
            return

        # Run summarization/sentiment in background thread, so (a) user can get back to business;
        # (b) if AI server offline, wait till online
        self.title_summary = "🕒 AI is generating a title"
        self.text_summary = "🕒 AI is generating a summary"
        db.session.add(Job(
            method='entry',
            data_in={'args': [str(self.id)]}
        ))


    def update_snoopers(self):
        """Updates snoopers with n_new_entries since last_seen"""
        sql = """
        with news as (
          select s.id, count(e.id) ct 
          from shares s 
          inner join shares_tags st on st.share_id=s.id
          inner join entries_tags et on et.tag_id=st.tag_id
          inner join entries e on e.id=et.entry_id
          where e.user_id=:uid 
            and e.created_at > s.last_seen
          group by s.id
        )
        update shares s set new_entries=n.ct from news n where n.id=s.id
        """
        db.session.execute(text(sql), {'uid': self.user_id})
        db.session.commit()


class SEntry(BaseModel):
    title: Optional[str] = None
    text: str
    no_ai: Optional[bool] = False


class SIEntry(SEntry):
    tags: dict
    created_at: Optional[str] = None


class SOEntry(SEntry, SOut):
    id: UUID4
    created_at: datetime.datetime
    ai_ran: Optional[bool] = None
    title_summary: Optional[str] = None
    text_summary: Optional[str] = None
    sentiment: Optional[str] = None
    entry_tags: Dict


class NoteTypes(enum.Enum):
    label = "label"
    note = "note"
    resource = "resource"


class Note(Base):
    __tablename__ = 'notes'
    id = IDCol()
    created_at = DateCol()
    entry_id = FKCol('entries.id', index=True)
    user_id = FKCol('users.id', index=True)
    type = Column(Enum(NoteTypes), nullable=False)
    text = Encrypt(Unicode, nullable=False)
    private = Column(Boolean, default=False)

    @staticmethod
    def snoop(
        viewer_id: UUID4,
        target_id: UUID4,
        entry_id: UUID4,
    ):
        # TODO use .join(ShareTag) for non-private permissions?
        return db.session.query(Note)\
            .join(Entry)\
            .filter(
                Note.entry_id == entry_id,
                or_(
                    # My own private note
                    and_(Note.private.is_(True), Note.user_id == viewer_id),
                    # Or this user can view it
                    and_(Note.private.is_(False), Entry.user_id.in_((viewer_id, target_id)))
                ))\
            .order_by(Note.created_at.asc())


class SINote(BaseModel):
    type: NoteTypes
    text: str
    private: bool


class SONote(SOut, SINote):
    id: UUID4
    user_id: UUID4
    created_at: datetime.datetime


class FieldType(enum.Enum):
    # medication changes / substance intake
    # exercise, sleep, diet, weight
    number = "number"

    # happiness score
    fivestar = "fivestar"

    # periods
    check = "check"

    # moods (happy, sad, anxious, wired, bored, ..)
    option = "option"

    # think of more
    # weather_api?
    # text entries?


class DefaultValueTypes(enum.Enum):
    value = "value"  # which includes None
    average = "average"
    ffill = "ffill"


class Field(Base):
    """Entries that change over time. Uses:
    * Charts
    * Effects of sentiment, topics on entries
    * Global trends (exercise -> 73% happiness)
    """
    __tablename__ = 'fields'

    id = IDCol()

    type = Column(Enum(FieldType))
    name = Encrypt()
    # Start entries/graphs/correlations here
    created_at = DateCol()
    # Don't actually delete fields, unless it's the same day. Instead
    # stop entries/graphs/correlations here
    excluded_at = DateCol(default=False)
    default_value = Column(Enum(DefaultValueTypes), default="value")
    default_value_value = Column(Float, default=None)
    target = Column(Boolean, default=False)
    # option{single_or_multi, options:[], ..}
    # number{float_or_int, ..}
    attributes = Column(JSON)
    # Used if pulling from external service
    service = Column(Unicode)
    service_id = Column(Unicode)

    user_id = FKCol('users.id', index=True)

    json_fields = """
    id
    name
    created_at
    excluded_at
    default_value_value
    target
    service
    service_id
    """

    def json(self):
        json_fields = {k: getattr(self, k) for k in self.json_fields.split()}
        history = db.session.query(FieldEntry)\
            .with_entities(FieldEntry.value, FieldEntry.created_at)\
            .filter_by(field_id=self.id)\
            .order_by(FieldEntry.created_at.asc())\
            .all()
        history = [
            dict(value=x.value, created_at=x.created_at)
            for x in history
            if x.value is not None
        ]

        return {
            **json_fields,
            'type': self.type.name,
            'default_value': self.default_value.name if self.default_value else "value",
            'avg': sum(x['value'] for x in history) / len(history) if history else 0.,
            'history': history
        }


class SIFieldExclude(BaseModel):
    excluded_at: Optional[datetime.datetime] = None


class SIField(SIFieldExclude):
    type: FieldType
    name: str
    default_value: DefaultValueTypes
    default_value_value: Optional[float] = None
    target: bool

## TODO can't get __root__ setup working
# class SFieldOut(SOut):
#     id: str
#     type: FieldType
#     name: str
#     created_at: Optional[Any] = None
#     excluded_at: Optional[Any] = None
#     default_value: Optional[M.DefaultValueTypes] = M.DefaultValueTypes.value
#     default_value_value: Optional[float] = None
#     target: Optional[bool] = False
#     service: Optional[str] = None
#     service_id: Optional[str] = None
#     history: Any
# class SFieldsOut(SOut):
#     __root__: Dict[str, SFieldOut]


class FieldEntry(Base):
    __tablename__ = 'field_entries'
    id = IDCol()
    value = Column(Float)  # TODO Can everything be a number? reconsider
    created_at = DateCol()

    user_id = FKCol('users.id', index=True)
    field_id = FKCol('fields.id')  # TODO index=True?

    @staticmethod
    def get_day_entries(user_id, day=None, field_id=None):
        tz_ = db.session.query(User.timezone).filter_by(id=user_id).scalar()
        tz_ = tz_ or 'America/Los_Angeles'

        timezoned = func.Date(func.timezone(tz_, FieldEntry.created_at))
        day = day.astimezone(tz.gettz(tz_)) if day else nowtz(tz_)

        q = db.session.query(FieldEntry)\
            .filter(FieldEntry.user_id == user_id, timezoned == day.date())
        if field_id:
            q = q.filter(FieldEntry.field_id == field_id)
        return q


class SIFieldEntry(BaseModel):
    value: float


class Person(Base):
    __tablename__ = 'people'
    id = IDCol()
    name = Encrypt()
    relation = Encrypt()
    issues = Encrypt()
    bio = Encrypt()

    user_id = FKCol('users.id', index=True)


class SIPerson(BaseModel):
    name: Optional[str] = None
    relation: Optional[str] = None
    issues: Optional[str] = None
    bio: Optional[str] = None


class SOPerson(SIPerson, SOut):
    id: UUID4
    pass


class Share(Base):
    __tablename__ = 'shares'
    id = IDCol()
    user_id = FKCol('users.id', index=True)
    email = Column(EmailType, index=True)  # TODO encrypt?

    fields = Column(Boolean)
    books = Column(Boolean)
    profile = Column(Boolean)

    share_tags = relationship("ShareTag", **parent_cascade)
    tags_ = relationship("Tag", secondary="shares_tags")

    last_seen = DateCol()
    new_entries = Column(Integer, default=0)

    @property
    def tags(self):
        return {t.tag_id: True for t in self.share_tags}


class SIShare(BaseModel):
    email: str
    fields_: Optional[bool] = False
    books: Optional[bool] = False
    profile: Optional[bool] = False
    tags: Optional[dict] = {}

    class Config:
        fields = {'fields_': 'fields'}


class SOShare(SIShare):
    id: UUID4

    class Config:
        fields = {'fields_': 'fields'}
        orm_mode = True


class Tag(Base):
    __tablename__ = 'tags'
    id = IDCol()
    user_id = FKCol('users.id', index=True)
    name = Encrypt(Unicode, nullable=False)
    # Save user's selected tags between sessions
    selected = Column(Boolean)
    main = Column(Boolean, default=False)

    shares = relationship("Share", secondary="shares_tags")

    @staticmethod
    def snoop(from_email, to_id, snooping=False):
        if snooping:
            return db.session.query(Tag)\
                .join(ShareTag, Share)\
                .filter(Share.email==from_email, Share.user_id == to_id)
        return db.session.query(Tag).filter_by(user_id=to_id)


class SITag(BaseModel):
    name: str
    selected: Optional[bool] = False


class SOTag(SITag, SOut):
    id: UUID4
    user_id: UUID4
    name: str
    selected: Optional[bool] = False
    main: Optional[bool] = False


class EntryTag(Base):
    __tablename__ = 'entries_tags'
    entry_id = FKCol('entries.id', primary_key=True)
    tag_id = FKCol('tags.id', primary_key=True)


class ShareTag(Base):
    __tablename__ = 'shares_tags'
    share_id = FKCol('shares.id', primary_key=True)
    tag_id = FKCol('tags.id', primary_key=True)

    tag = relationship(Tag, backref=backref("tags"))
    share = relationship(Share, backref=backref("shares"))


class Book(Base):
    __tablename__ = 'books'
    id = Column(Integer, primary_key=True)
    title = Column(Unicode, nullable=False)
    text = Column(Unicode, nullable=False)
    author = Column(Unicode)
    topic = Column(Unicode)

    thumbs = Column(Integer, default=0)
    amazon = Column(Unicode)


class Shelves(enum.Enum):
    ai = "ai"
    like = "like"
    already_read = "already_read"
    dislike = "dislike"
    remove = "remove"
    recommend = "recommend"


class Bookshelf(Base):
    __tablename__ = 'bookshelf'
    created_at = DateCol()
    updated_at = DateCol(update=True)

    book_id = Column(Integer, primary_key=True)  # no FK, books change often
    user_id = FKCol('users.id', primary_key=True)
    shelf = Column(Enum(Shelves), nullable=False)
    score = Column(Float)  # only for ai-recs

    @staticmethod
    def update_books(user_id):
        with db():
            # every x thumbs, update book recommendations
            sql = """
            select count(*)%8=0 as ct from bookshelf 
            where user_id=:uid and shelf!='ai'
            """
            should_update = db.session.execute(text(sql), {'uid':user_id}).fetchone().ct
            if should_update:
                db.session.add(Jobs(
                    method='books',
                    data_in={'args': [str(user_id)]}
                ))
                db.session.commit()

    @staticmethod
    def upsert(user_id, book_id, shelf):
        db.session.execute(text("""
        insert into bookshelf(book_id, user_id, shelf)  
        values (:book_id, :user_id, :shelf)
        on conflict (book_id, user_id) do update set shelf=:shelf
        """), dict(user_id=user_id, book_id=int(book_id), shelf=shelf))

        dir = dict(ai=0, like=1, already_read=1, dislike=-1, remove=0, recommend=1)[shelf]
        db.session.execute(text("""
        update books set thumbs=thumbs+:dir where id=:bid
        """), dict(dir=dir, bid=book_id))

        db.session.commit()
        threading.Thread(target=Bookshelf.update_books, args=(user_id,)).start()

    @staticmethod
    def get_shelf(user_id, shelf):
        is_cool = db.session.query(User.is_cool).filter_by(id=user_id).scalar()
        books = db.session.execute(text(f"""
        select b.id, b.title, {"b.text" if is_cool else "'' as text"}, b.author, b.topic, b.amazon
        from books b 
        inner join bookshelf bs on bs.book_id=b.id 
            and bs.user_id=:uid and bs.shelf=:shelf
        """), dict(uid=user_id, shelf=shelf)).fetchall()
        print(len(books))
        return books
        # return [dict(b) for b in books]


class Job(Base):
    __tablename__ = 'jobs'
    id = IDCol()
    created_at = DateCol()
    updated_at = DateCol(update=True)
    method = Column(Unicode)
    state = Column(Unicode, default='new')
    data_in = Column(JSONB)
    data_out = Column(JSONB)


class JobsStatus(Base):
    __tablename__ = 'jobs_status'
    id = Column(Integer, primary_key=True)
    status = Column(Unicode)
    ts_client = DateCol()
    ts_svc = DateCol()
    svc = Column(Unicode)


class SILimitEntries(BaseModel):
    days: int
    tags: List[str] = None


class SIQuestion(SILimitEntries):
    query: str


class SISummarize(SILimitEntries):
    words: int



###
# Cache models, storing data for use after machine learning runs
###

class CacheEntry(Base):
    __tablename__ = 'cache_entries'
    entry_id = FKCol('entries.id', primary_key=True)
    paras = Encrypt(array=True)
    clean = Encrypt(array=True)
    vectors = Column(ARRAY(Float, dimensions=2))

    @staticmethod
    def get_paras(entries_q, profile_id=None):
        entries = entries_q.join(CacheEntry, CacheEntry.entry_id == Entry.id) \
            .filter(CacheEntry.paras.isnot(None)) \
            .with_entities(CacheEntry.paras).all()
        paras = [p for e in entries for p in e.paras if e.paras]

        if profile_id:
            profile = db.session.query(CacheUser) \
                .filter(CacheUser.paras.isnot(None), CacheUser.user_id == profile_id) \
                .with_entities(CacheUser.paras) \
                .first()
            if profile:
                paras = profile.paras + entries

        return paras


class CacheUser(Base):
    __tablename__ = 'cache_users'
    user_id = FKCol('users.id', primary_key=True)

    # profile nlp
    paras = Encrypt(array=True)
    clean = Encrypt(array=True)
    vectors = Column(ARRAY(Float, dimensions=2))

    # influencers all general
    last_influencers = DateCol()
    influencers = Column(JSONB)

    last_books = DateCol()


def await_row(sess, sql, args={}, wait=.5, timeout=None):
    i = 0
    while True:
        res = sess.execute(text(sql), args).fetchone()
        if res: return res
        time.sleep(wait)
        if timeout and wait * i >= timeout:
            return None
        i += 1