"""RDHS 专题浏览器会话与登录编排。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

from shared.browser.browser_fetcher import run_playwright_eval
from shared.browser.browser_session import ensure_browser_session_ready
from shared.browser.managed_session import close_browser_session
from shared.browser.managed_session import generate_managed_session_name
from shared.browser.managed_session import open_browser_session
from shared.browser.managed_session import save_storage_state
from shared.browser.managed_session import try_load_storage_state

DEFAULT_USERNAME_SELECTORS = [
    "input[name='email']",
    "input[name='username']",
    "input[name='account']",
    "input[type='email']",
    "input[type='text']",
]
DEFAULT_PASSWORD_SELECTORS = [
    "input[name='password']",
    "input[type='password']",
]
DEFAULT_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('登录')",
    "button:has-text('Log in')",
    "button:has-text('Sign in')",
]
DEFAULT_ENTRANCE_SELECTORS = [
    "button:has-text('i讯飞登录')",
    "text=i讯飞登录",
    "button:has-text('iflychat login entrance')",
    "button:has-text('Account Login')",
    "text=iflychat login entrance",
    "text=Account Login",
]
_MAX_MANAGED_SESSION_NAME_LENGTH = 20


def _run_playwright_code(session_name: str, script: str) -> None:
    subprocess.run(
        ["playwright-cli", f"-s={session_name}", "run-code", script],
        check=True,
        capture_output=True,
        text=True,
    )


def _goto_without_networkidle(session_name: str, url: str) -> None:
    subprocess.run(
        ["playwright-cli", f"-s={session_name}", "goto", url],
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_rdhs_browser_session(session_name: str) -> bool:
    ok, _reason = ensure_browser_session_ready(session_name)
    return ok


def browser_requires_login(session_name: str) -> bool:
    ok, _reason = ensure_browser_session_ready(session_name)
    return not ok


def read_browser_page_state(session_name: str) -> dict:
    return run_playwright_eval(
        session_name,
        """() => ({
          href: window.location.href,
          title: document.title,
          body: (document.body?.innerText || '').slice(0, 300)
        })""",
    )


def resolve_login_attempt_url(*, current_state: dict, dashboard_config) -> str:
    current_href = str(current_state.get("href", "")).strip()
    if (
        "accounts.xfchat.iflytek.com/accounts/page/login" in current_href
        and "redirect_uri=" in current_href
    ):
        return current_href
    return dashboard_config.login_url or dashboard_config.view_url


def build_login_script(
    *,
    login_url: str,
    username: str,
    password: str,
    username_selector: str = "",
    password_selector: str = "",
    submit_selector: str = "",
    sso_domain: str = "",
    sso_provider: str = "i讯飞登录",
) -> str:
    user_selectors = [username_selector] if username_selector else []
    password_selectors = [password_selector] if password_selector else []
    submit_selectors = [submit_selector] if submit_selector else []
    user_selectors.extend(DEFAULT_USERNAME_SELECTORS)
    password_selectors.extend(DEFAULT_PASSWORD_SELECTORS)
    submit_selectors.extend(DEFAULT_SUBMIT_SELECTORS)
    entrance_selectors = DEFAULT_ENTRANCE_SELECTORS

    return f"""async page => {{
      const userSelectors = {json.dumps(user_selectors, ensure_ascii=False)};
      const passwordSelectors = {json.dumps(password_selectors, ensure_ascii=False)};
      const submitSelectors = {json.dumps(submit_selectors, ensure_ascii=False)};
      const entranceSelectors = {json.dumps(entrance_selectors, ensure_ascii=False)};
      const ssoDomain = {json.dumps(sso_domain, ensure_ascii=False)};
      const ssoProvider = {json.dumps(sso_provider, ensure_ascii=False)};

      async function pick(selectors) {{
        for (const selector of selectors) {{
          const locator = page.locator(selector).first();
          if (await locator.count()) {{
            return locator;
          }}
        }}
        return null;
      }}

      const currentUrl = page.url();
      await page.goto({json.dumps(login_url, ensure_ascii=False)}, {{ waitUntil: 'domcontentloaded' }});
      await page.waitForTimeout(1500);

      if (!currentUrl.includes('sso.iflytek.com')) {{
        const existingUser = await pick(userSelectors);
        const existingPass = await pick(passwordSelectors);
        if (!existingUser || !existingPass) {{
          const entrance = await pick(entranceSelectors);
          if (entrance) {{
            try {{
              await entrance.click({{ force: true }});
            }} catch (error) {{
              await entrance.evaluate(node => node.click());
            }}
            await page.waitForTimeout(2500);
          }}
        }}
      }}

      if (page.url().includes('iflytek.com')) {{
        const switchCandidates = ['账号登录', '密码登录', 'Account Login', 'Password Login'];
        const switched = await page.evaluate((candidates) => {{
          const buttons = Array.from(document.querySelectorAll('button, a, span'));
          for (const el of buttons) {{
            const text = (el.textContent || '').trim();
            if (candidates.some(c => text.includes(c))) {{
              el.click();
              return text;
            }}
          }}
          return '';
        }}, switchCandidates);
        if (switched) {{
          await page.waitForTimeout(1500);
        }}
      }}

      if (ssoDomain) {{
        const domainInput = page.getByPlaceholder('Enter your company domain').last();
        if (await domainInput.count()) {{
          await domainInput.fill(ssoDomain);
          if (ssoProvider) {{
            const providerInput = page.getByPlaceholder('Please select').last();
            if (await providerInput.count()) {{
              await providerInput.click();
              await page.waitForTimeout(500);
              const providerOption = page.getByText(ssoProvider).last();
              if (await providerOption.count()) {{
                await providerOption.click();
                await page.waitForTimeout(500);
              }}
            }}
          }}
          const next = page.getByRole('button', {{ name: 'Next' }}).last();
          if (await next.count()) {{
            await next.click();
            await page.waitForTimeout(1500);
          }}
        }}
      }}

      const user = await pick(userSelectors);
      const pass = await pick(passwordSelectors);
      if (!user || !pass) {{
        throw new Error('login form fields not found');
      }}

      await user.fill({json.dumps(username, ensure_ascii=False)});
      await pass.fill({json.dumps(password, ensure_ascii=False)});

      const loginButton = page.getByRole('button', {{ name: '登录' }}).first();
      if (await loginButton.count()) {{
        await loginButton.click();
      }} else {{
        const submit = await pick(submitSelectors);
        if (submit) {{
          await submit.click();
        }} else {{
          await pass.press('Enter');
        }}
      }}

      try {{
        await page.waitForLoadState('networkidle', {{ timeout: 15000 }});
      }} catch (error) {{
      }}
      await page.waitForTimeout(3000);
    }}"""


def login_with_credentials(
    *,
    session_name: str,
    login_url: str,
    username: str,
    password: str,
    username_selector: str = "",
    password_selector: str = "",
    submit_selector: str = "",
    sso_domain: str = "",
    sso_provider: str = "i讯飞登录",
) -> None:
    script = build_login_script(
        login_url=login_url,
        username=username,
        password=password,
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        sso_domain=sso_domain,
        sso_provider=sso_provider,
    )
    _run_playwright_code(session_name, script)


def prepare_managed_rdhs_session(
    *, dashboard_config, auth_config, project_root: Path
) -> str:
    storage_state_path = Path(dashboard_config.storage_state_path)
    if not storage_state_path.is_absolute():
        storage_state_path = project_root / storage_state_path

    configured_session_name = dashboard_config.session_name
    if configured_session_name:
        if len(configured_session_name) > _MAX_MANAGED_SESSION_NAME_LENGTH:
            session_name = generate_managed_session_name(configured_session_name)
        else:
            session_name = configured_session_name
    else:
        session_name = generate_managed_session_name(prefix="rdhs-report")
    start_url = dashboard_config.view_url or dashboard_config.login_url
    open_browser_session(
        session_name=session_name,
        start_url=start_url,
        headless=dashboard_config.headless,
    )
    try_load_storage_state(
        session_name=session_name,
        storage_state_path=storage_state_path,
    )
    _goto_without_networkidle(session_name=session_name, url=dashboard_config.view_url)

    if browser_requires_login(session_name):
        login_with_credentials(
            session_name=session_name,
            login_url=resolve_login_attempt_url(
                current_state=read_browser_page_state(session_name),
                dashboard_config=dashboard_config,
            ),
            username=auth_config.username,
            password=auth_config.password,
            sso_domain=auth_config.sso_domain,
            sso_provider=auth_config.sso_provider,
            username_selector=auth_config.username_selector,
            password_selector=auth_config.password_selector,
            submit_selector=auth_config.submit_selector,
        )
        subprocess.run(
            [
                "playwright-cli",
                f"-s={session_name}",
                "run-code",
                "async page => { await page.waitForTimeout(3000); }",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        current_state = read_browser_page_state(session_name)
        if "project.xfchat.iflytek.com" not in str(current_state.get("href", "")):
            _goto_without_networkidle(
                session_name=session_name, url=dashboard_config.view_url
            )
            current_state = read_browser_page_state(session_name)

        ok = not browser_requires_login(session_name)
        attempts = 0
        while not ok and attempts < 5:
            attempts += 1
            time.sleep(3)
            ok = not browser_requires_login(session_name)

        if not ok:
            current_state = read_browser_page_state(session_name)
            raise RuntimeError(
                "自动登录失败，页面仍停留在登录态: "
                f"href={current_state.get('href', '')} "
                f"title={current_state.get('title', '')}"
            )
        save_storage_state(
            session_name=session_name,
            storage_state_path=storage_state_path,
        )

    return session_name


__all__ = [
    "browser_requires_login",
    "build_login_script",
    "close_browser_session",
    "ensure_rdhs_browser_session",
    "login_with_credentials",
    "open_browser_session",
    "prepare_managed_rdhs_session",
    "read_browser_page_state",
    "resolve_login_attempt_url",
    "save_storage_state",
    "try_load_storage_state",
]
