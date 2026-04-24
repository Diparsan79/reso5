from browser import document, html, aio, window
import json

BASE = ""
api_key = None
delete_id = None

# get local storage from window
ls = window.localStorage


def flash(msg, err=False):
    el = document["flash"]
    el.text = msg
    el.className = "err" if err else ""
    el.style.display = "block"


def set_key_status(msg):
    document["key-status"].text = msg


def stars(n):
    n = int(n)
    return "★" * n + "☆" * (5 - n)


# on page load
def init():
    global api_key
    saved = ls.getItem("api_key")
    if saved:
        api_key = saved
        set_key_status("key: " + api_key[:10] + "...")
        flash("welcome back! key loaded.")
        aio.run(refresh())
    else:
        flash("register above to get started.")


async def refresh():
    await fetch_list()
    await fetch_stats()


# register
async def do_register(ev):
    global api_key
    name = document["reg-name"].value.strip()
    if not name:
        flash("type your name first", err=True)
        return
    flash("registering...")
    req = await aio.post(
        BASE + "/register",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"name": name})
    )
    if req.status == 200:
        data = json.loads(req.data)
        api_key = data["api_key"]
        ls.setItem("api_key", api_key)
        document["reg-name"].value = ""
        set_key_status("key: " + api_key[:10] + "...")
        flash("registered! key saved in browser.")
        aio.run(refresh())
    else:
        flash("registration failed: " + str(req.status), err=True)


def do_forget(ev):
    global api_key
    api_key = None
    ls.removeItem("api_key")
    set_key_status("not logged in")
    document["list-container"].innerHTML = '<div id="empty-msg">nothing here. add something above.</div>'
    for sid in ["s-total","s-watched","s-unwatched","s-movies","s-series","s-rating"]:
        document[sid].text = "—"
    flash("key forgotten.")


# fetch + render list
async def fetch_list(type_f=None, watched_f=None):
    if not api_key:
        return
    url = BASE + "/watchlist"
    params = []
    if type_f:
        params.append("type=" + type_f)
    if watched_f:
        params.append("watched=" + watched_f)
    if params:
        url += "?" + "&".join(params)

    req = await aio.get(url, headers={"x-api-key": api_key})
    if req.status == 200:
        items = json.loads(req.data)
        render_list(items)
    else:
        flash("failed to load list: " + str(req.status), err=True)


def render_list(items):
    c = document["list-container"]
    c.innerHTML = ""
    if not items:
        c <= html.DIV("nothing here. add something above.", id="empty-msg")
        return
    for item in items:
        c <= make_card(item)


def make_card(item):
    card = html.DIV(Class="movie-card")

    # title row
    title_row = html.DIV()
    watched = item["watched"]
    b_status = html.SPAN("watched" if watched else "unwatched",
                         Class="badge badge-watched" if watched else "badge badge-unwatched")
    b_type = html.SPAN(item["type"],
                       Class="badge badge-movie" if item["type"] == "movie" else "badge badge-series")
    title_row <= b_status
    title_row <= b_type
    card <= title_row

    # title
    card <= html.DIV(item["title"], Class="card-title")

    # meta
    meta = item["genre"] + " · added " + item["added_at"][:10]
    if item["rating"]:
        meta += " · " + stars(item["rating"])
    if item["review"]:
        meta += ' · "' + item["review"] + '"'
    card <= html.DIV(meta, Class="card-meta")

    # action buttons
    actions = html.DIV(Class="card-actions")

    # mark watched button
    if not watched:
        btn_w = html.BUTTON("mark watched", Class="tiny")
        item_id = item["id"]
        def watch_handler(ev, iid=item_id):
            aio.run(do_watch(iid))
        btn_w.bind("click", watch_handler)
        actions <= btn_w

    # delete button
    btn_d = html.BUTTON("delete", Class="tiny ghost")
    item_id = item["id"]
    def del_handler(ev, iid=item_id, title=item["title"]):
        open_modal(iid, title)
    btn_d.bind("click", del_handler)
    actions <= btn_d

    card <= actions

    # rate form — only show if watched and not yet rated
    if watched and not item["rating"]:
        rate_div = html.DIV(Class="rate-inline")
        r_in = html.INPUT(type="number", placeholder="1-5", id="r-" + str(item["id"]))
        r_in.attrs["min"] = "1"
        r_in.attrs["max"] = "5"
        rv_in = html.INPUT(type="text", placeholder="review (optional)", id="rv-" + str(item["id"]))
        btn_r = html.BUTTON("rate", Class="tiny")
        item_id = item["id"]
        def rate_handler(ev, iid=item_id):
            aio.run(do_rate(iid))
        btn_r.bind("click", rate_handler)
        rate_div <= r_in
        rate_div <= rv_in
        rate_div <= btn_r
        card <= rate_div

    return card


# add item
async def do_add(ev):
    if not api_key:
        flash("register first!", err=True)
        return
    title = document["add-title"].value.strip()
    genre = document["add-genre"].value.strip()
    typ = document["add-type"].value
    if not title or not genre:
        flash("fill in title and genre", err=True)
        return
    flash("adding...")
    req = await aio.post(
        BASE + "/watchlist",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        data=json.dumps({"title": title, "type": typ, "genre": genre})
    )
    if req.status == 200:
        document["add-title"].value = ""
        document["add-genre"].value = ""
        flash("added: " + title)
        aio.run(refresh())
    else:
        try:
            flash(json.loads(req.data).get("detail", "error"), err=True)
        except Exception:
            flash("error " + str(req.status), err=True)


# mark watched
async def do_watch(item_id):
    req = await aio.ajax(
        "PATCH",
        BASE + "/watchlist/" + str(item_id) + "/watched",
        headers={"x-api-key": api_key, "Content-Type": "application/json"}
    )
    if req.status == 200:
        flash("marked as watched!")
        aio.run(refresh())
    else:
        flash("error " + str(req.status), err=True)


# rate
async def do_rate(item_id):
    r_el = document["r-" + str(item_id)]
    rv_el = document["rv-" + str(item_id)]
    rating = r_el.value.strip()
    review = rv_el.value.strip()
    if not rating:
        flash("enter a rating 1-5", err=True)
        return
    payload = {"rating": int(rating)}
    if review:
        payload["review"] = review
    req = await aio.ajax(
        "PATCH",
        BASE + "/watchlist/" + str(item_id) + "/rate",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        data=json.dumps(payload)
    )
    if req.status == 200:
        flash("rated!")
        aio.run(fetch_list())
    else:
        try:
            flash(json.loads(req.data).get("detail", "error"), err=True)
        except Exception:
            flash("error " + str(req.status), err=True)


# delete modal
def open_modal(item_id, title):
    global delete_id
    delete_id = item_id
    document["modal-msg"].text = 'delete "' + title + '"? this cannot be undone.'
    document["modal"].className = "show"


def close_modal(ev):
    document["modal"].className = ""


async def confirm_delete(ev):
    global delete_id
    close_modal(None)
    if delete_id is None:
        return
    iid = delete_id
    delete_id = None
    req = await aio.ajax(
        "DELETE",
        BASE + "/watchlist/" + str(iid),
        headers={"x-api-key": api_key, "Content-Type": "application/json"}
    )
    if req.status == 200:
        flash("deleted.")
        aio.run(refresh())
    else:
        flash("delete failed " + str(req.status), err=True)


# search
async def do_search(ev):
    if not api_key:
        flash("register first!", err=True)
        return
    q = document["search-q"].value.strip()
    if not q:
        aio.run(fetch_list())
        return
    flash("searching...")
    req = await aio.get(
        BASE + "/watchlist/search?q=" + q,
        headers={"x-api-key": api_key}
    )
    if req.status == 200:
        data = json.loads(req.data)
        results = data.get("results", [])
        render_list(results)
        flash(str(len(results)) + " result(s) for: " + q)
    else:
        flash("search error " + str(req.status), err=True)


def do_reset(ev):
    document["search-q"].value = ""
    document["f-type"].value = ""
    document["f-watched"].value = ""
    aio.run(fetch_list())


def do_filter(ev):
    typ = document["f-type"].value or None
    w = document["f-watched"].value or None
    aio.run(fetch_list(type_f=typ, watched_f=w))


# stats
async def fetch_stats():
    if not api_key:
        return
    req = await aio.get(BASE + "/watchlist/stats", headers={"x-api-key": api_key})
    if req.status == 200:
        s = json.loads(req.data)
        document["s-total"].text = str(s["total"])
        document["s-watched"].text = str(s["watched"])
        document["s-unwatched"].text = str(s["unwatched"])
        document["s-movies"].text = str(s["movies"])
        document["s-series"].text = str(s["series"])
        document["s-rating"].text = str(s["average_rating"]) if s["average_rating"] else "—"


# bind all buttons
document["btn-register"].bind("click", do_register)
document["btn-forget"].bind("click", do_forget)
document["btn-add"].bind("click", do_add)
document["btn-search"].bind("click", do_search)
document["btn-reset"].bind("click", do_reset)
document["btn-confirm-del"].bind("click", confirm_delete)
document["btn-cancel-del"].bind("click", close_modal)

# filter on dropdown change
document["f-type"].bind("change", do_filter)
document["f-watched"].bind("change", do_filter)

# search on enter key
def search_enter(ev):
    if ev.key == "Enter":
        aio.run(do_search(ev))
document["search-q"].bind("keydown", search_enter)

init()