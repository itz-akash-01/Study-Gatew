# Study_Gateway AI — animated welcome / login page

Three files, no libraries, no build step, no external images or fonts:

| File | What it is |
|---|---|
| `index.html` | The page (logo, heading, puppies, login card, footer, icon sprite) |
| `welcome.css` | Pastel liquid-glass design + all animations |
| `welcome.js` | Form checks, show/hide password, paw trails, hearts, and the **integration block** |

## 1. See it on your computer (30 seconds)
Double-click `index.html`. It opens in your browser.
In this "preview mode" the Google button only shows a note, because Google sign-in needs your Flask server.

## 2. Add it to your Flask / Vercel project
1. Copy this whole `welcome` folder into your project's `static/` folder, so you have `static/welcome/index.html`.
2. Add this small route to `sg_app/routes.py` (inside `register(app)`):
   ```python
   @app.route("/welcome")
   def welcome():
       return redirect("/static/welcome/index.html")
   ```
3. Run your site and open `http://localhost:5000/welcome`.
4. Optional: to make it your main sign-in page, change the `login()` route to `return redirect("/welcome")`.

The page already works with the security setup from the secured project: it has no inline scripts or inline event handlers and loads nothing from other websites, so your strict Content-Security-Policy allows it as-is.

## 3. What is real and what is pending
| Item | Status |
|---|---|
| **Continue with Google** | **Real.** A normal link to `/auth/google` (Supabase + Google). Nothing is simulated. |
| Dashboard redirect | **Real.** After Google sign-in your Flask app sends the user to `/`. |
| Protected pages | Still protected by the **server** (`login_required`), not by this page. |
| Email + password "Log in" | **Pending.** Your backend has no email/password login (we left it out on purpose). The form validates input, then says honestly that it isn't switched on. It never fakes a login. Integration point: `CONFIG.emailLogin` at the top of `welcome.js`. |
| Create account / Forgot password? | **Pending.** They show a friendly "coming soon" note. Set `CONFIG.createAccountUrl` / `forgotPasswordUrl` when those pages exist. |

Password safety: the page never stores, logs or sends the password anywhere on its own. When you build email login, send it only to your own server over HTTPS with the CSRF token, and let the server (Supabase Auth) do the hashing. No secret keys ever go in this JavaScript.

## 4. The puppies (please read)
The reference picture you sent is one flat image with its background baked in, so the puppies can't be cut out of it cleanly. I redrew two puppies as **vector characters in the same style** (cream puppy with pink heart bandana, golden puppy with flower and a wink). Because they are drawn in layers, the **tail wags, ears flop, legs trot and eyes blink** for real.

They enter with a bounce, then loop (16 s): run right, pause and hop, run back, change direction, a playful feint, run left, pause and hop. The second puppy follows slightly behind at a different depth. They leave paw prints and occasionally float hearts. Everything stays inside their own area above the card (it is clipped, so they can never cover inputs or buttons).

- **Small screens:** puppies shrink and run a shorter distance automatically.
- **Reduced motion:** if the visitor's device asks for reduced motion, all animation stops and the puppies stand still facing each other.
- **Hidden tab / scrolled away:** paw and heart effects pause.
- **Your own artwork:** send me a transparent PNG of each puppy and I will swap it in. A flat PNG can only bounce, hop, tilt and slide; it cannot wag or trot.

Tweak speed: change `--dur:16s` in `.pup` (bigger = slower). Colours: the `:root` block at the top of `welcome.css`.

## 5. What was tested
Passed (32 automated checks in a simulated browser): empty / bad-email / empty-password messages, focus on first error, show/hide password, Google link target, pending notices, failed and crashed login hook (generic message, password cleared, button re-enabled), safe-redirect rule, paw trails appear and stay capped, no effects in reduced-motion mode, no duplicate ids, every icon and aria reference resolves, every input has a label, no inline scripts, no external requests, layout order and all required texts present. The puppy and logo drawings were rendered to images and checked by eye.

**Not tested** (no real browser was available): the actual on-screen look, smoothness of the animations, the mobile layout on real phones, and Google sign-in end to end. Open it on your phone and laptop and check: no sideways scrolling, puppies stay above the card, text readable. Tell me anything that looks off and I'll fix it.
