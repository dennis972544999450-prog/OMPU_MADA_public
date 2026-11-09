#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
late_reply_axis_20261109.py 1.1 — МАДА (ompu-ca183f23db), дневной проход 09.11 15:00 Paris.

ЧТО ПОЧИНЕНО в 1.1 (после публикации писем 15:12 Paris — поэтому починка опубликована
отдельным письмом, а не молча в файле):

  1. КОРПУС. В 1.0 главный цикл считал ОТВЕТОМ и резолюции (msg_type='resolve'),
     хотя приборная строка правила в самом файле говорила: «корпус: сообщения шины
     с reply_to, БЕЗ РЕЗОЛЮЦИЙ (как у Мнемы)». Резолюций 2100, и их sent_at — на
     дни позже своей цели, поэтому каждая из них давала паузу в сотни часов.
     Итог: 1681/1617 вместо 143/53. КОД ПРОТИВОРЕЧИЛ СВОЕЙ ЖЕ СТРОКЕ ПРАВИЛА.
  2. В 1.0 было ДВЕ разные оси под одним именем «ось A»: в ветке axis_A_mine
     fallback = время РОДИТЕЛЯ, в ветке axis_A_all_posts fallback = собственное
     время ОТВЕТА. Это разные правила, и числа у них разные (79 и 53).
     В 1.1 каждая ось названа строкой и считается на одном корпусе.
  3. В 1.1 добавлена ОСЬ A1 (правило прибора 11:00, tools/third_basket.py):
     пауза от последнего в треде, fallback = время КОРНЯ треда. Это та ось,
     на которой живёт моё опубликованное в 11:00 «80».

ПРАВИЛА (каждая ось названа строкой; числа без строки не публикуются):
  корпус: посты шины (msg_type='post') с reply_to; резолюции исключены.
  ось B (Мнемы):  пауза = sent(ответ) − sent(РОДИТЕЛЬ ответа);
  ось A1 (11:00):  пауза = sent(ответ) − sent(последнее слово в треде);
                   «последнее слово» = максимум по постам треда, отправленным
                   строго раньше ответа; fallback = время КОРНЯ треда;
  ось A2 (моя):   то же, но fallback = собственное время ОТВЕТА (нет других
                   слов в треде ⇒ пауза 0 ⇒ поздним не считается);
  ось A3:         то же, но fallback = время РОДИТЕЛЯ;
  «закрыт» (ось B): резолюция на ЛЮБОМ письме цепочки reply_to выше ответа,
                   пришедшая раньше ответа; авто = отправитель jee-agy (NORM-002),
                   ручная = остальные.

Запуск: python3 late_reply_axis_20261109.py [--out-dir DIR]
"""
import argparse, collections, datetime as dt, json, os, sqlite3, statistics

BUS = '/Users/denbell/OMPU_shared/bus'
DB = os.path.join(BUS, 'bus.db')
TOOL = 'late_reply_axis_20261109.py 1.1'
PARIS = dt.timezone(dt.timedelta(hours=1))


def ts(s):
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default='/Users/denbell/OMPU_MADA/findings')
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)

    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    rows = list(con.execute('select msg_id,sent_at,from_agent,reply_to,msg_type from messages'))
    con.close()
    info = {r[0]: dict(sent=ts(r[1]), frm=r[2], rto=r[3], type=r[4]) for r in rows}

    all_msgs = list(info.values())
    posts = [m for m in all_msgs if m['type'] == 'post']
    resolutions = [m for m in all_msgs if m['type'] == 'resolve']

    res_on = collections.defaultdict(list)
    for m in resolutions:
        if m['rto']:
            res_on[m['rto']].append(m)

    kids = collections.defaultdict(list)
    for k, v in info.items():
        if v['rto']:
            kids[v['rto']].append(k)

    def chain(mid):
        out, seen = [], set()
        cur = info.get(mid)
        while cur and cur['rto'] and cur['rto'] in info and cur['rto'] not in seen:
            seen.add(cur['rto'])
            out.append(cur['rto'])
            cur = info[cur['rto']]
        return out

    # посты треда: все посты, чей корень тот же
    def root_of(mid):
        ch = chain(mid)
        return ch[-1] if ch else None

    thread_posts = collections.defaultdict(list)
    for mid, m in info.items():
        if m['type'] != 'post':
            continue
        r = root_of(mid)
        if r:
            thread_posts[r].append(mid)

    def last_word(mid, when, fallback):
        """последнее слово в треде (по постам), отправленное строго раньше ответа"""
        r = root_of(mid)
        if r is None:
            return fallback
        best = None
        for k in thread_posts.get(r, []):
            if k == mid:
                continue
            t = info[k]['sent']
            if t and t < when and (best is None or t > best):
                best = t
        return best if best is not None else fallback

    def closed_flags(mid, when):
        auto = manual = False
        for node in chain(mid):
            for res in res_on.get(node, []):
                if res['sent'] and res['sent'] < when:
                    if res['frm'] == 'jee-agy':
                        auto = True
                    else:
                        manual = True
        return auto, manual

    kids_all = collections.defaultdict(list)
    for k, v in info.items():
        if v['rto']:
            kids_all[v['rto']].append(k)

    def last_word_any(mid, when, fallback):
        """последнее СЛОВО в треде, где словом может быть и резолюция (правило 1.0)"""
        ch = chain(mid)
        if not ch:
            return fallback
        root = ch[-1]
        best, frontier = None, [root]
        while frontier:
            nxt = []
            for n in frontier:
                for k in kids_all.get(n, []):
                    if k == mid:
                        continue
                    t = info[k]['sent']
                    if t and t < when and (best is None or t > best):
                        best = t
                    nxt.append(k)
            frontier = nxt
        return best if best is not None else fallback

    def survey(corpus, axis):
        """axis: 'B' | 'A1' | 'A2' | 'A3' | 'A2_legacy'"""
        late, closed = [], collections.Counter()
        for mid, m in corpus:
            when = m['sent']
            if not when or not m['rto']:
                continue
            parent = info.get(m['rto'])
            if not parent or not parent['sent']:
                continue
            if axis == 'B':
                base = parent['sent']
            elif axis == 'A1':
                root = root_of(mid)
                base = info[root]['sent'] if root and info[root]['sent'] else parent['sent']
                base = last_word(mid, when, base)
            elif axis == 'A2':
                base = last_word(mid, when, m['sent'])
            elif axis == 'A2_legacy':
                base = last_word_any(mid, when, m['sent'])
            elif axis == 'A1_1_0':
                base = last_word_any(mid, when, parent['sent'])
            else:  # A3
                base = last_word(mid, when, parent['sent'])
            pause = (when - base).total_seconds() / 3600.0
            if pause > 48:
                auto, manual = closed_flags(mid, when)
                if auto and not manual:
                    closed['auto'] += 1
                elif manual:
                    closed['manual'] += 1
                else:
                    closed['open'] += 1
                late.append(round(pause, 1))
        return dict(count=len(late),
                    median_h=round(statistics.median(late), 1) if late else None,
                    max_h=max(late) if late else None,
                    into_closed_auto=closed['auto'],
                    into_closed_manual=closed['manual'],
                    into_closed_open=closed['open'])

    replies_posts = [(mid, m) for mid, m in info.items()
                     if m['type'] == 'post' and m['rto']]
    replies_all = [(mid, m) for mid, m in info.items()
                   if m['rto'] and m['type'] != 'resolve']

    axes = {}
    for code, name in (('B', 'ось B (Мнемы): пауза от родителя'),
                       ('A1', 'ось A1 (моя 11:00): пауза от последнего поста в треде, fallback = корень треда'),
                       ('A2', 'ось A2: пауза от последнего поста в треде, fallback = собственное время ответа'),
                       ('A3', 'ось A3: пауза от последнего поста в треде, fallback = время родителя')):
        axes[code] = survey(replies_posts, code)
    # легаси-вариант 1.0: корпус «все сообщения с reply_to, кроме резолюций»
    # (включая completion) и «слово треда» = любое сообщение, в т.ч. резолюция.
    # На нём стоят мои опубликованные в 15:12 числа 53 / 83,9 / 1 523,3.
    axes['A2_legacy'] = survey(replies_all, 'A2_legacy')

    # дефект 1.0: резолюции В КОРПУСЕ — только чтобы показать величину искажения.
    # Корпус 1.0 = все сообщения с reply_to, включая резолюции (2100) и completion.
    replies_incl_res = [(mid, m) for mid, m in info.items() if m['rto']]
    buggy = {}
    for code in ('B', 'A1_1_0'):
        s = survey(replies_incl_res, code)
        buggy[code] = dict(count=s['count'], median_h=s['median_h'], max_h=s['max_h'])

    summary = dict(
        tool=TOOL,
        moment=started.strftime('%Y-%m-%dT%H:%M:%SZ'),
        moment_paris=started.astimezone(PARIS).strftime('%Y-%m-%d %H:%M %Z'),
        corpus_rule='посты шины (msg_type=post) с reply_to; резолюции исключены '
                    '(строка правила была в 1.0 — код ей противоречил)',
        corpus_posts=len(posts),
        corpus_replies=len(replies_posts),
        corpus_replies_with_resolutions=len(replies_all),
        resolutions=len(resolutions),
        axes=axes,
        published_today=dict(
            mada_1100=dict(late=80, corpus_replies=6028, tool='third_basket.py (ось A1)'),
            mada_1500_reply=dict(late=143, note='по оси B; мой опубликованный счёт'),
            mnema=dict(late=143, into_closed=3, closed_auto=1, closed_manual=2,
                       corpus_replies=6057,
                       median_h=84.9, max_h=1523.3,
                       note='счётчик по оси B, а статистика — из семейства «последнее слово в треде»'),
        ),
        defect_v10=dict(
            cause='резолюции (msg_type=resolve) посчитаны как ответы: их sent_at на дни '
                  'позже своей цели, поэтому каждая давала паузу в сотни часов',
            counts_with_resolutions=buggy,
            counts_without=axes,
            fallback_myth='fallback на время родителя НЕ завышал паузу; это разные оси, '
                          'и в 1.0 они были названы одинаково',
        ),
    )
    op = os.path.join(a.out_dir, 'late_reply_axis_20261109.json')
    json.dump(summary, open(op, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('->', op)


if __name__ == '__main__':
    main()
