from pathlib import Path
from typing import Self

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

from ..models import LocatorKind, LocatorSpec, Observation


class PlaywrightSurface:
    """Browser surface adapter. Artifact/replay code does not depend on Playwright directly."""

    def __init__(
        self,
        *,
        headless: bool,
        action_timeout_ms: int,
    ):
        self.headless = headless
        self.action_timeout_ms = action_timeout_ms
        self._pw: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def __enter__(self) -> Self:
        self._pw = sync_playwright().start()

        self.browser = self._pw.chromium.launch(
            headless=self.headless
        )

        self.context = self.browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            }
        )

        self.page = self.context.new_page()

        self.page.set_default_timeout(
            self.action_timeout_ms
        )

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self._pw:
            self._pw.stop()

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError(
                "Surface is not started; "
                "use it as a context manager"
            )

        return self.page

    def goto(
        self,
        url: str,
    ) -> None:
        self._require_page().goto(
            url,
            wait_until="domcontentloaded",
        )

    def _resolve(
        self,
        spec: LocatorSpec,
    ) -> Locator:
        page = self._require_page()

        if spec.kind == LocatorKind.ROLE:
            return page.get_by_role(
                spec.value,
                name=spec.name,
                exact=spec.exact,
            )

        if spec.kind == LocatorKind.LABEL:
            return page.get_by_label(
                spec.value,
                exact=spec.exact,
            )

        if spec.kind == LocatorKind.TEXT:
            return page.get_by_text(
                spec.value,
                exact=spec.exact,
            )

        if spec.kind == LocatorKind.CSS:
            return page.locator(
                spec.value
            )

        raise ValueError(
            "Unsupported locator kind: "
            f"{spec.kind}"
        )

    def _form_control_state(self) -> str:
        page = self._require_page()

        controls = page.locator(
            "input, textarea, select"
        )

        states: list[str] = []

        for index in range(
            controls.count()
        ):
            control = controls.nth(index)

            try:
                tag_name = control.evaluate(
                    "(element) => "
                    "element.tagName.toLowerCase()"
                )

                input_type = (
                    (
                        control.get_attribute(
                            "type"
                        )
                        or "text"
                    )
                    if tag_name == "input"
                    else tag_name
                )

                name = control.get_attribute(
                    "name"
                )

                control_id = (
                    control.get_attribute(
                        "id"
                    )
                )

                aria_label = (
                    control.get_attribute(
                        "aria-label"
                    )
                )

                label = None

                if control_id:
                    associated_label = (
                        page.locator(
                            f'label[for="{control_id}"]'
                        )
                    )

                    if (
                        associated_label.count()
                        > 0
                    ):
                        label = (
                            associated_label
                            .first
                            .inner_text()
                            .strip()
                        )

                if not label:
                    try:
                        label = (
                            control.evaluate(
                                """(element) => {
                                    const label =
                                        element.closest("label");
                                    return label
                                        ? label.innerText.trim()
                                        : null;
                                }"""
                            )
                        )
                    except PlaywrightError:
                        label = None

                if input_type in {
                    "checkbox",
                    "radio",
                }:
                    value = str(
                        control.is_checked()
                    ).lower()

                    state_name = "checked"

                else:
                    value = (
                        control.input_value()
                    )

                    state_name = "value"

                parts = [
                    (
                        f"{tag_name} "
                        f"type={input_type!r}"
                    )
                ]

                if label:
                    parts.append(
                        f"label={label!r}"
                    )

                if aria_label:
                    parts.append(
                        "aria-label="
                        f"{aria_label!r}"
                    )

                if name:
                    parts.append(
                        f"name={name!r}"
                    )

                if control_id:
                    parts.append(
                        f"id={control_id!r}"
                    )

                parts.append(
                    f"{state_name}={value!r}"
                )

                states.append(
                    "- " + " ".join(parts)
                )

            except PlaywrightError:
                continue

        if not states:
            return "[no form controls]"

        return "\n".join(states)

    def observe(self) -> Observation:
        page = self._require_page()
        body = page.locator("body")

        try:
            aria = body.aria_snapshot(
                timeout=2_000
            )
        except PlaywrightError:
            aria = (
                "[accessibility snapshot "
                "unavailable]"
            )

        text = body.inner_text(
            timeout=2_000
        )

        form_state = (
            self._form_control_state()
        )

        accessibility_snapshot = (
            f"{aria}\n\n"
            "CURRENT FORM CONTROL STATE:\n"
            f"{form_state}"
        )

        return Observation(
            url=page.url,
            title=page.title(),
            visible_text=text[:12_000],
            accessibility_snapshot=(
                accessibility_snapshot[
                    :20_000
                ]
            ),
        )

    def click(
        self,
        locator: LocatorSpec,
        timeout_ms: int,
    ) -> None:
        self._resolve(
            locator
        ).click(
            timeout=timeout_ms
        )

    def fill(
        self,
        locator: LocatorSpec,
        value: str,
        timeout_ms: int,
    ) -> None:
        self._resolve(
            locator
        ).fill(
            value,
            timeout=timeout_ms,
        )

    def extract(
        self,
        locator: LocatorSpec,
        timeout_ms: int,
    ) -> str:
        return (
            self._resolve(locator)
            .inner_text(
                timeout=timeout_ms
            )
            .strip()
        )

    def text_present(
        self,
        text: str,
    ) -> bool:
        return (
            self._require_page()
            .get_by_text(
                text,
                exact=False,
            )
            .count()
            > 0
        )

    def screenshot(
        self,
        path: str,
    ) -> None:
        destination = Path(path)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._require_page().screenshot(
            path=str(destination),
            full_page=True,
        )
