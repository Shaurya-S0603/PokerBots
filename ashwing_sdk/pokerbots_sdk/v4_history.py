from collections import defaultdict,deque
class PublicHistory:
    def __init__(self):self.match_id=None;self.completed=set();self.rows=defaultdict(lambda:deque(maxlen=96))
    def start(self,match_id):
        if match_id!=self.match_id:self.match_id=match_id;self.completed.clear();self.rows.clear()
    def record(self,hand_id,actions):
        if hand_id is None or hand_id in self.completed:return
        self.completed.add(hand_id)
        for a in actions:
            if a.get('is_timeout'):continue
            if a.get('phase',a.get('street')) in ('flop','turn','river') and a['action'] in ('raise','call','fold','check'):self.rows[a.get('seat',a.get('player_id'))].append(a['action'])
    def aggression(self,pid):
        rows=self.rows.get(pid,());return (2+sum(x=='raise' for x in rows))/(8+len(rows)),len(rows)
