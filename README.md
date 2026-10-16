# Free Instagram autoposter (GitHub Actions + Graph API)

## One-time setup
1. **Account:** Instagram must be a Business or Creator account linked to a Facebook Page.
2. **Meta app:** create an app at developers.facebook.com (type: Business), add the
   "Instagram Graph API" product. Permissions: `instagram_basic`,
   `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`.
   For your own account, the app can stay in Development mode (no app review).
3. **Token (no 60-day refresh):**
   - In Graph API Explorer, generate a User token with the permissions above.
   - Exchange it for a long-lived user token:
     `GET /oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN`
   - Call `GET /me/accounts` with the long-lived token. The `access_token`
     returned for your Page is a **Page token that does not expire**. Use that one.
4. **IG user ID:** `GET /PAGE_ID?fields=instagram_business_account` -> use the `id` inside.
5. **Repo secrets** (Settings -> Secrets and variables -> Actions):
   `IG_USER_ID` and `IG_ACCESS_TOKEN`.
6. Push this folder to a GitHub repo and enable Actions.

## Using the queue (`queue.csv`)
| column | notes |
|---|---|
| id | any unique value |
| type | `IMAGE`, `REELS` or `CAROUSEL` |
| media_urls | public URL(s); separate carousel items with `\|` (2-10) |
| caption / hashtags | hashtags are appended after a blank line |
| publish_at | UTC ISO time, e.g. `2026-10-20T09:00:00Z` |
| status / post_id / error | filled in by the script; leave blank for new rows |

A row is posted once `publish_at` has passed and `status` is blank.
Fix an `error` row by clearing its status and error cells.

## Media hosting
- **Images:** the repo must be public to use raw.githubusercontent.com URLs, and JPEG is safest.
- **Videos/reels:** use Cloudflare R2 (free tier) with a public bucket URL. Raw GitHub
  serves videos with a generic content type, which Instagram often rejects.
- Reels: MP4 (H.264/AAC), 9:16, 3 s to 15 min. Keep files reasonably small.

## Testing
- Locally: `DRY_RUN=1 python publisher.py`
- In GitHub: Actions -> Publish Instagram posts -> Run workflow (tick dry run).
- First real test: schedule one IMAGE post a few minutes in the past.

## Notes
- Graph API publishing is capped at about 100 posts per 24 h per account.
- API posts can't use trending audio; post those from the app.
- GitHub cron is best effort, so posts may go out a few minutes late.
- Update `GRAPH_VERSION` in the script occasionally as Meta retires old versions.
