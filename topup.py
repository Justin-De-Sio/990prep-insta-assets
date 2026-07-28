"""Réapprovisionne quotidiennement la file Buffer (plan gratuit = 10 posts programmés max).

Lit manifest.json (173 carrousels TikTok, ordre chronologique) et state.json
(prochain index à programmer), puis complète la file du canal Instagram
jusqu'à 10 posts, à raison d'un créneau par jour à 09:00 UTC.
"""
import json
import os
import sys
import datetime
import urllib.request

TOKEN = os.environ["BUFFER_TOKEN"]
CHANNEL = "6a68e6a64b2d03035f58693c"
ORG = "6a68e50da6debabf55d35e10"
RAW = "https://raw.githubusercontent.com/Justin-De-Sio/990prep-insta-assets/main/images"
MAX_QUEUE = 10
DUE_HOUR_UTC = 9  # 11h Paris l'été, 10h l'hiver


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.buffer.com",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"])[:500])
    return body["data"]


def scheduled_posts():
    q = """query($org: OrganizationId!, $ch: [ChannelId!]) {
      posts(input: {organizationId: $org,
                    filter: {status: [scheduled], channelIds: $ch},
                    sort: [{field: dueAt, direction: asc}]}) {
        edges { node { id dueAt } }
      }
    }"""
    d = gql(q, {"org": ORG, "ch": [CHANNEL]})
    return [e["node"] for e in d["posts"]["edges"]]


def create_post(post, due):
    q = """mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id dueAt } }
        ... on MutationError { message }
      }
    }"""
    assets = [{"image": {"url": f"{RAW}/{post['id']}/{i:02d}.jpg"}}
              for i in range(1, min(post["count"], 10) + 1)]
    d = gql(q, {"input": {
        "text": post["title"],
        "channelId": CHANNEL,
        "schedulingType": "automatic",
        "mode": "customScheduled",
        "dueAt": due.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "assets": assets,
        "metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}},
    }})
    res = d["createPost"]
    if "post" not in res:
        raise RuntimeError(res.get("message", "échec createPost"))
    return res["post"]["id"]


def main():
    manifest = json.load(open("manifest.json"))
    state = json.load(open("state.json"))
    idx = state["next_index"]

    if idx >= len(manifest):
        print(f"Manifest épuisé ({len(manifest)} posts publiés ou programmés). Rien à faire.")
        return

    queue = scheduled_posts()
    slots = MAX_QUEUE - len(queue)
    print(f"File: {len(queue)}/{MAX_QUEUE} — {slots} créneau(x) libre(s), prochain index: {idx}")
    if slots <= 0:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    if queue:
        last_due = datetime.datetime.fromisoformat(
            max(p["dueAt"] for p in queue).replace("Z", "+00:00"))
        next_due = last_due + datetime.timedelta(days=1)
    else:
        next_due = (now + datetime.timedelta(days=1)).replace(
            hour=DUE_HOUR_UTC, minute=0, second=0, microsecond=0)

    for _ in range(slots):
        if idx >= len(manifest):
            break
        post = manifest[idx]
        buffer_id = create_post(post, next_due)
        print(f"  index {idx} ({post['id']}) programmé pour {next_due.date()} -> {buffer_id}")
        idx += 1
        state["next_index"] = idx
        json.dump(state, open("state.json", "w"))
        next_due += datetime.timedelta(days=1)

    print(f"Terminé. Prochain index: {idx}/{len(manifest)}")


if __name__ == "__main__":
    main()
