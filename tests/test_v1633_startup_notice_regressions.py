import tempfile,tkinter as tk,unittest
from pathlib import Path
from desktop_layout import scroll_frame,bind_direct_scroll_subtree
from knowledge_update import KnowledgeUpdater

class NotificationWheelTests(unittest.TestCase):
    def test_wheel_over_child_label_is_not_bar_only(self):
        try:r=tk.Tk()
        except tk.TclError:self.skipTest('Graphical Tk display required')
        self.addCleanup(r.destroy)
        w=tk.Toplevel(r);w.geometry('440x270+60+60')
        shell,body=scroll_frame(w,'#061522');shell.pack(fill='both',expand=True)
        cards=[]
        for i in range(40):
            card=tk.Frame(body);card.pack(fill='x')
            title=tk.Label(card,text='Notification '+str(i),height=2);title.pack(fill='x');cards.append(title)
        bind_direct_scroll_subtree(body,shell._scroll_canvas)
        r.update_idletasks();r.update()
        canvas=shell._scroll_canvas
        before=canvas.yview()[0]
        cards[1].event_generate('<MouseWheel>',delta=-120)
        r.update()
        self.assertGreater(canvas.yview()[0],before)
        before=canvas.yview()[0]
        cards[3].event_generate('<MouseWheel>',delta=-120)
        r.update()
        self.assertGreater(canvas.yview()[0],before)

class StartupIdleTests(unittest.TestCase):
    def test_auto_refresh_deferred_but_manual_not_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            cfg={'knowledge':{'mode':'automatic','enabled':True,'interval_hours':24}}
            u=KnowledgeUpdater(cfg,Path(d),clock=lambda:1000)
            # Set delay without starting a worker thread, then mimic user refresh.
            from unittest.mock import patch
            with patch('threading.Thread') as thread:
                thread.return_value.is_alive.return_value=True
                u.start(initial_delay_seconds=45)
            self.assertGreaterEqual(u.next_due,1045)
            u.refresh()
            self.assertEqual(u.next_due,0)

if __name__=='__main__':unittest.main()
