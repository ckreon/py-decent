
# These classes mainly deal with database interaction

import datetime
import json
import uuid


import requests

from voluptuous import Schema, Required, All, Length, MultipleInvalid, Range

from voat_sql.utils      import db
from voat_utils.config   import get_config
from voat_utils.updater  import send_thread
from voat_sql.utils.user import UserUtils



class SubvoatUtils():
    def __init__(self):
        self.db         = db.get_db()
        self.classes    = self.db.base.classes
        self.config     = get_config()
        self.user_utils = UserUtils()
   

    # Returns a user object (see the schemas)
    def create_subvoat_object(self, **kwargs):
        return self.classes.subvoat(**kwargs)


    def create_thread_object(self, **kwargs):
        return self.classes.thread(**kwargs)

    def create_comment_object(self, **kwargs):
        return self.classes.comment(**kwargs)


    # Returns a user object 
    def get_subvoat(self, subvoat_name):
        return self.db.session.query(self.classes.subvoat).filter(self.classes.subvoat.name == subvoat_name).first()
 
    def get_comments(self, thread_uuid):
        return self.db.session.query(self.classes.thread).filter(self.classes.thread.uuid == thread_uuid).first().comment_collection


    def get_all_subvoats(self):
        return self.db.session.query(self.classes.subvoat).all()

    
    def add_subvoat(self, new_subvoat):
        self.db.session.add(new_subvoat)
        
        result = self.db.session.commit()

        return result


    def add_comment(self, thread_uuid, body, user_obj, reply_uuid=None):
        
        thread = self.get_thread_by_uuid(thread_uuid)

        if not thread:
            return [False, 'no such thread']

        if reply_uuid:
            new_comment = self.create_comment_object(body=body, 
                                                 user_id=user_obj.id, 
                                                 uuid=str(uuid.uuid4()), 
                                                 creation_date=datetime.datetime.utcnow(),
                                                 reply_uuid=reply_uuid)

        else:
            new_comment = self.create_comment_object(body=body, 
                                                 user_id=user_obj.id, 
                                                 uuid=str(uuid.uuid4()), 
                                                 creation_date=datetime.datetime.utcnow())

        thread.comment_collection.append(new_comment)

        if not self.db.session.commit():
            return [True, 'added']

        return [False, 'unable to add comment']


    # Returns [result, message]
    def add_thread(self, subvoat_name, title, body, username):

        schema = Schema({ 
            Required('subvoat_name'): All(str, Length(min=self.config['min_length_subvoat_name'])),
            Required('title'):        All(str, Length(min=self.config['min_length_thread_title'])),
            Required('body'):         All(str, Length(min=self.config['min_length_thread_body'])),
            })


        try:
            schema({'subvoat_name':subvoat_name,
                    'title':title,
                    'body':body})

        except MultipleInvalid as e:
            return [False, '%s %s' % (e.msg, e.path)]


        subvoat = self.get_subvoat(subvoat_name)

        if not subvoat:
            return [False, 'subvoat does not exist']

        # We need to use the user.id  
    
        status, result = self.user_utils.get_user(username)

        if not status:
            return [False, result]

       
        # Should this even be here?
        elif not result:
            return [False, 'user does not exist']

        now = datetime.datetime.utcnow()
        new_thread = self.create_thread_object(uuid=str(uuid.uuid4()),
                                           title=title,
                                           body=body,
                                           user_id=result.id,
                                           creation_date=now)

        subvoat.thread_collection.append(new_thread)

        self.db.session.commit()


        # JUST TESTING, FIX THIS (MAKE IT ASYNC, OTHERWISE IT WILL BLOCK)

        send_thread.delay()

        return [True, 'thread added']

        
    # Make one that orders by date, with a limit
    def get_all_threads(self, subvoat_name):
        threads = []
        subvoat =  self.db.session.query(self.classes.subvoat).filter(self.classes.subvoat.name == subvoat_name).first()


        # probably want to limit this
        #if subvoat:
        #    for thread in subvoat.thread_collection:
                # Need to convert the user_id to username
                #u_result, u_obj = self.user_utils.get_user_by_id(thread.user_id)

                #f u_result == False:
                    # LOG ERROR HERE
                    # error message should be in u_obj
                #   continue 

            
            

        return subvoat.thread_collection

    def get_thread_by_uuid(self, uuid):
        thread = self.db.session.query(self.classes.thread).filter(self.classes.thread.uuid == uuid).first()


        return thread

    
    def vote_thread(self, thread_uuid, direction, user_id):

        schema = Schema({ Required('direction'):   All(int, Range(min=-1, max=1)),
                          Required('thread_uuid'): All(str, Length(min=36, max=36)),
            })

        try:
            schema({'direction':direction, 'thread_uuid':thread_uuid})

        except MultipleInvalid as e:
            return [False, '%s %s' % (e.msg, e.path)]

        
        thread = self.get_thread_by_uuid(thread_uuid)

        if not thread:
            return [False, 'no such thread']

        # see if the user already voted, if so change the vote direction if its different 
        sq = self.db.session.query(self.classes.thread).filter(self.classes.thread.uuid == thread_uuid).subquery()
        
        q  = self.db.session.query(self.classes.vote, sq).filter(self.classes.vote.user_id == user_id).first()

    
        # if the vote doesn't exist, create it and commit it
        if not q:
            new_vote = self.classes.vote(user_id=user_id, direction=direction)

            thread.vote_collection.append(new_vote)

            self.db.session.add(thread)

            if not self.db.session.commit():
                return [True, 'vote added']

            return [False, 'unable to commit vote']


        # If the vote is the same
        if q.direction == int(direction):
            return [True, 'vote unchanged']

        # Otherwise update the vote direction 
        else:
            q.direction = int(direction)
            self.db.session.add(q)

            if not self.db.session.commit():
                return [True, 'vote changed']
       
            return [False, 'unable to commit vote change'] 


