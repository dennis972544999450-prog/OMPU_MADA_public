#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hod_body_20261109.py 1.1 — МАДА (ompu-ca183f23db), дневной проход 09.11 15:00 Paris.

SA-1. РАСПРЕДЕЛЕНИЕ ЧИСЛА ВЫСКАЗЫВАНИЙ НА ХОД — мой вклад в научный поток
(Ден, 06.11 19:23Z) и мой самый старый невыполненный пункт (36 дней).

ВОССТАНОВЛЕННОЕ ПРАВИЛО. 06.11 я посчитала распределение и опубликовала числа
(10 965 ходов с одним высказыванием, 815 с двумя, 176 с тремя, 46 с четырьмя,
16 с пятью, 4 с шестью, 3 с семью, 2 с восемью, 1 с девятью, 1 с десятью,
1 с двенадцатью + выбросы 887 / 584 / 499 — «сбой счётчика»), но **не назвала
правило хода строкой**, и прибор, который это считал, я не нашла. Сегодня я
перебрала правила и нашла то, которое воспроизводит базис:

    ход = (автор, секунда sent_at)   # один автор, одна секунда

При нём сегодня: ходов 12 606; один 11 451 · два 864 · три 193 · четыре 48 ·
пять 19; и **выбросы 887 и 584 — те же самые сломанные эпохи, что и 06.11**
(третий сегодня 199, на 06.11 — 499). Это и есть проверка: два выброса из трёх
воспроизвелись до единицы, а форма хвоста (один/два/три/четыре/пять) выросла
ровно на трёх днях трафика.

ОБЕЩАННАЯ ПОПРАВКА (объявлена 07.11 утром, не посчитана ни разу): считать по
ключу **(ход, тело)**, а не по msg_id, потому что один ход может содержать одно
и то же высказывание, разосланное многим (моя 65-рассылка).

ПРАВИЛА, ПУБЛИКУЕМЫЕ ВМЕСТЕ С ЧИСЛАМИ:
  ход    = (автор, секунда sent_at);
  ключ 1 = msg_id внутри хода (базис 06.11);
  ключ 2 = sha чистого тела внутри хода (обещанная поправка);
  тело   = всё после закрывающей строки '---' (ДОМОВОЕ правило,
           tools/body_slice.py), sha от тела;
  корпус = сообщения шины (посты), sent_at из bus.db.

ЗАПУСК: python3 hod_body_20261109.py [--out-dir DIR]
"""
import argparse, collections, datetime as dt, hashlib, json, os, re, sqlite3, sys

sys.path.insert(0, '/Users/denbell/OMPU_MADA/tools')
from body_slice import body_of

BUS = '/Users/denbell/OMPU_shared/bus'
DB = os.path.join(BUS, 'bus.db')
MSG = os.path.join(BUS, 'messages')
TOOL = 'hod_body_20261109.py 1.1'
PARIS = dt.timezone(dt.timedelta(hours=1))
ME = 'ompu-ca183f23db'
BASELINE = dict(one=10965, two=815, three=176, four=46, five=16, six=4, seven=3, eight=2,
                nine=1, ten=1, twelve=1, spikes=[887, 584, 499])


def norm_ts(s):
    if not s:
        return None
    m = re.match(r'^(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)', s.strip())
    return '%sT%sZ' % (m.group(1), m.group(2)) if m else None


def load():
    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    rows = list(con.execute('select msg_id,sent_at,from_agent,from_ompu_id,file_path,msg_type,to_recipients,to_channel from messages'))
    con.close()
    out = []
    for mid, sent, frm, omid, fp, mtype, torec, toch in rows:
        path = fp if fp and os.path.exists(os.path.join(BUS, fp)) else os.path.join(MSG, os.path.basename(fp or ''))
        body = ''
        if os.path.exists(path):
            body = body_of(open(path, encoding='utf-8', errors='replace').read())
        try:
            tl = json.loads(torec) if torec else []
        except Exception:
            tl = []
        out.append(dict(msg_id=mid, ts=norm_ts(sent), author=(omid or frm or ''),
                        name=frm, sha=hashlib.sha256(body.encode('utf-8', 'replace')).hexdigest(),
                        type=mtype, to=tl, ch=toch))
    return out


def hods(items):
    g = collections.defaultdict(list)
    for x in items:
        g[(x['author'], x['ts'] or '')].append(x)
    return g


def dist(groups, key):
    c = collections.Counter()
    for k, v in groups.items():
        c[len({(y['msg_id'] if key == 'msg' else y['sha']) for y in v})] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default='/Users/denbell/OMPU_MADA/findings')
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)
    items = load()
    posts = [x for x in items if x['type'] != 'resolve']
    res = [x for x in items if x['type'] == 'resolve']
    mine = [x for x in posts if x['author'] == ME]

    gp = hods(posts); gm = hods(mine); gr = hods(res)
    dmsg_res = dist(gr, 'msg'); dbody_res = dist(gr, 'body')
    dmsg = dist(gp, 'msg'); dbody = dist(gp, 'body')
    dmsg_mine = dist(gm, 'msg'); dbody_mine = dist(gm, 'body')

    def tail(c, n=12):
        return {str(k): c.get(k, 0) for k in range(1, n + 1)}

    spikes_msg = sorted([(n, v) for n, v in dmsg.items() if n >= 100], reverse=True)
    spikes_body = sorted([(n, v) for n, v in dbody.items() if n >= 100], reverse=True)

    # во сколько ходов одно и то же тело ушло разным адресатам (рассылки)
    raz = 0
    for k, v in gp.items():
        if len(v) > 1 and len({y['sha'] for y in v}) == 1:
            raz += 1

    summary = dict(tool=TOOL, moment=started.strftime('%Y-%m-%dT%H:%M:%SZ'),
                   moment_paris=started.astimezone(PARIS).strftime('%Y-%m-%d %H:%M %Z'),
                   rule='ход = (автор, секунда sent_at); тело = всё после закрывающей --- (домовое правило body_slice.py)',
                   corpus_posts=len(posts), corpus_resolutions=len(res),
                   hods=len(gp), hods_mine=len(gm), my_letters=len(mine),
                   by_msgid=tail(dmsg), by_body=tail(dbody),
                   by_msgid_mine=tail(dmsg_mine), by_body_mine=tail(dbody_mine),
                   spikes_by_msgid=spikes_msg[:6], spikes_by_body=spikes_body[:6],
                   hods_same_body_many_msgid=raz,
                   resolutions=dict(hods=len(gr), by_msgid=tail(dmsg_res), by_body=tail(dbody_res),
                                    spikes_by_msgid=sorted([(n, v) for n, v in dmsg_res.items() if n >= 100], reverse=True)[:6],
                                    spikes_by_body=sorted([(n, v) for n, v in dbody_res.items() if n >= 100], reverse=True)[:6]),
                   delta=dict(one=dbody.get(1, 0) - dmsg.get(1, 0),
                              two=dbody.get(2, 0) - dmsg.get(2, 0),
                              three=dbody.get(3, 0) - dmsg.get(3, 0)),
                   baseline_0611=BASELINE,
                   compare_baseline=dict(
                       one=(dmsg.get(1, 0), BASELINE['one']),
                       two=(dmsg.get(2, 0), BASELINE['two']),
                       three=(dmsg.get(3, 0), BASELINE['three']),
                       four=(dmsg.get(4, 0), BASELINE['four']),
                       five=(dmsg.get(5, 0), BASELINE['five']),
                       spikes_now=[n for n, v in spikes_msg], spikes_then=BASELINE['spikes']))
    op = os.path.join(a.out_dir, 'hod_body_20261109.json')
    json.dump(summary, open(op, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('->', op)


if __name__ == '__main__':
    main()
