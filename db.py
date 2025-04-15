import sqlite3



class Database:
    def __init__(self):
        self.connection = sqlite3.connect('db.sqlite3')
        self.cursor = self.connection.cursor()

    def execute(self, query, params=()):
        self.cursor.execute(query, params)
        self.connection.commit()
        result = self.cursor.fetchall()
        return result

    def close(self):
        self.connection.close()


if __name__ == '__main__':
    db = Database()
    print(db.execute('SELECT * FROM administration_bot'))
    db.close()
