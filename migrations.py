# migrations.py is for building your database

async def m001_initial(db):
   await db.execute(
       f"""
       CREATE TABLE mqttln.device (
           device_id TEXT
       );
   """
   )
