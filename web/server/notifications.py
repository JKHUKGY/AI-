"""持久邮件队列。发送失败保留待办并重试，不静默丢弃使用通知。"""
from email.message import EmailMessage
from email.utils import formatdate
import smtplib
import ssl
import time
import control_store as store


def configured(config=None):
    config = config or store.settings()
    return all(config.get(k) for k in ('mail_to', 'smtp_host', 'smtp_user', 'smtp_password', 'mail_from'))


def send(message, config):
    cls = smtplib.SMTP_SSL if config.get('smtp_security', 'ssl') == 'ssl' else smtplib.SMTP
    kwargs = {'timeout': 15}
    if cls is smtplib.SMTP_SSL:
        kwargs['context'] = ssl.create_default_context()
    with cls(config['smtp_host'], int(config.get('smtp_port', 465)), **kwargs) as client:
        if cls is smtplib.SMTP:
            client.starttls(context=ssl.create_default_context())
        client.login(config['smtp_user'], config['smtp_password'])
        client.send_message(message)


def deliver_one():
    config = store.settings()
    if not configured(config):
        return
    with store.db() as c:
        row = c.execute("SELECT o.*,u.username,u.project,u.kind,u.quantity,u.unit_cost,u.created_at FROM outbox o JOIN usage u ON u.id=o.usage_id WHERE o.status!='sent' AND o.next_try<=? ORDER BY u.created_at LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return
        row = dict(row)
        c.execute('UPDATE outbox SET next_try=?,attempts=attempts+1 WHERE id=?', (time.time()+120, row['id']))
    message = EmailMessage()
    message['From'], message['To'] = config['mail_from'], config['mail_to']
    message['Subject'] = '剧本家协作台：账号使用通知'
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = '<' + row['usage_id'] + '@scriptwriter.local>'
    labels = {'image':'图片生成', 'video':'视频生成', 'gpu':'租用显卡', 'prompt':'提示词生成', 'setup':'项目筹备', 'help':'帮助问答', 'login':'登录', 'mail_test':'管理员通知测试'}
    message.set_content(f"账号：{row['username']}\n项目：{row['project'] or '无'}\n操作：{labels.get(row['kind'], row['kind'])}\n数量：{row['quantity']}\n预计积分：{row['quantity'] * row['unit_cost']}\n任务编号：{row['usage_id']}\n时间（UTC）：{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(row['created_at']))}\n请在管理员页面查看进度、结算及租卡费用。")
    try:
        send(message, config)
    except Exception:
        with store.db() as c:
            c.execute("UPDATE outbox SET status='failed', error=?,next_try=? WHERE id=?", ('发信失败，请检查 SMTP 配置、授权码和网络', time.time()+min(3600, 30*2**min(row['attempts'],7)), row['id']))
    else:
        with store.db() as c:
            c.execute("UPDATE outbox SET status='sent',error=NULL,sent_at=? WHERE id=?", (time.time(), row['id']))


def status():
    with store.db() as c:
        counts = {r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM outbox GROUP BY status')}
        errors = [dict(r) for r in c.execute("SELECT usage_id,error,attempts FROM outbox WHERE status='failed' ORDER BY next_try DESC LIMIT 10")]
    return {'configured':configured(), 'counts':counts, 'errors':errors}
