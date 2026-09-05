#!/usr/bin/env python3
"""管理剧本家协作网站的登录账号（公网部署时用）。

    python3 web/server/manage_users.py add <用户名> [--name 显示名]
    python3 web/server/manage_users.py passwd <用户名>
    python3 web/server/manage_users.py remove <用户名>
    python3 web/server/manage_users.py list
    python3 web/server/manage_users.py grant <用户名> <剧名> [剧名2 ...]
    python3 web/server/manage_users.py grant-admin <用户名>
    python3 web/server/manage_users.py revoke-admin <用户名>

密码用交互式 getpass 输入，不会出现在命令行历史/进程列表里。

新建账号默认**什么项目都看不到**，必须用 grant 显式授权能看哪几部剧，
或者用 grant-admin 设成管理员（能看全部剧）——这是故意"默认拒绝"的设计，
避免漏配置导致意外看到不该看的剧。
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth
import control_store


def _prompt_password():
    while True:
        pw1 = getpass.getpass('设置密码：')
        if len(pw1) < 8:
            print('密码至少 8 位，重来。')
            continue
        pw2 = getpass.getpass('再输入一次确认：')
        if pw1 != pw2:
            print('两次输入不一致，重来。')
            continue
        return pw1


def cmd_add(args):
    users = auth.load_users()
    if args.username in users:
        print(f'用户 {args.username} 已存在，如果是要改密码请用 passwd 子命令。')
        sys.exit(1)
    password = _prompt_password()
    auth.add_user(args.username, password, args.name)
    print(f'已添加用户 {args.username}。')


def cmd_passwd(args):
    users = auth.load_users()
    if args.username not in users:
        print(f'用户 {args.username} 不存在。')
        sys.exit(1)
    password = _prompt_password()
    auth.add_user(args.username, password, users[args.username].get('display_name'))
    control_store.set_enabled(args.username, bool(control_store.account(args.username)['enabled']))
    print(f'已更新 {args.username} 的密码。')


def cmd_remove(args):
    if auth.remove_user(args.username):
        print(f'已删除用户 {args.username}。')
    else:
        print(f'用户 {args.username} 不存在。')
        sys.exit(1)


def _perm_summary(username):
    allowed = auth.allowed_projects(username)
    if allowed is None:
        return '管理员（看全部）'
    if not allowed:
        return '无权限（还没 grant）'
    return '、'.join(allowed)


def cmd_list(args):
    users = auth.load_users()
    if not users:
        print('目前没有任何账号。')
        return
    for name, info in users.items():
        print(f"{name}\t{info.get('display_name', name)}\t{_perm_summary(name)}")


def cmd_grant(args):
    users = auth.load_users()
    if args.username not in users:
        print(f'用户 {args.username} 不存在，先用 add 建账号。')
        sys.exit(1)
    auth.set_projects(args.username, args.projects)
    print(f'已设置 {args.username} 能看：{"、".join(args.projects)}（覆盖式设置，不是追加）')


def cmd_grant_admin(args):
    users = auth.load_users()
    if args.username not in users:
        print(f'用户 {args.username} 不存在，先用 add 建账号。')
        sys.exit(1)
    auth.set_admin(args.username, True)
    print(f'已把 {args.username} 设为管理员（能看全部剧）。')


def cmd_revoke_admin(args):
    auth.set_admin(args.username, False)
    print(f'已取消 {args.username} 的管理员权限（现在什么都看不到，需要重新 grant）。')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_add = sub.add_parser('add', help='新增一个账号')
    p_add.add_argument('username')
    p_add.add_argument('--name', default=None, help='显示名（默认等于用户名）')
    p_add.set_defaults(func=cmd_add)

    p_passwd = sub.add_parser('passwd', help='重置某个账号的密码')
    p_passwd.add_argument('username')
    p_passwd.set_defaults(func=cmd_passwd)

    p_remove = sub.add_parser('remove', help='删除某个账号')
    p_remove.add_argument('username')
    p_remove.set_defaults(func=cmd_remove)

    p_list = sub.add_parser('list', help='列出所有账号')
    p_list.set_defaults(func=cmd_list)

    p_grant = sub.add_parser('grant', help='设置某个账号能看哪几部剧（覆盖式设置）')
    p_grant.add_argument('username')
    p_grant.add_argument('projects', nargs='+', help='剧名（output/ 下的目录名），可以传多个')
    p_grant.set_defaults(func=cmd_grant)

    p_grant_admin = sub.add_parser('grant-admin', help='把某个账号设为管理员（能看全部剧）')
    p_grant_admin.add_argument('username')
    p_grant_admin.set_defaults(func=cmd_grant_admin)

    p_revoke_admin = sub.add_parser('revoke-admin', help='取消某个账号的管理员权限')
    p_revoke_admin.add_argument('username')
    p_revoke_admin.set_defaults(func=cmd_revoke_admin)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
