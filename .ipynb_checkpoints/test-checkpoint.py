# from datetime import datetime
# print("hi")
# print(datetime.now())
print("HEY")
with open("/Users/davidkatz/Documents/Jupyter_Notebooks/Jobs-Notifier/testlog.log", "a") as f:
    f.write(f"Cron test: hi\n")