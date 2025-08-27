from apscheduler.schedulers.background import BackgroundScheduler


class Scheduler:
    def __init__(self):
        self.sched = BackgroundScheduler()
        self.sched.start()

    def once(self, run_date, func, **kwargs):
        self.sched.add_job(func, 'date', run_date=run_date, kwargs=kwargs)

    def cron(self, cron_expr: str, func, **kwargs):
        m, h, dom, mon, dow = cron_expr.split()
        self.sched.add_job(func, 'cron', minute=m, hour=h, day=dom, month=mon, day_of_week=dow, kwargs=kwargs)


