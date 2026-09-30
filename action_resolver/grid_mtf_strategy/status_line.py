from rich.text import Text

from action_resolver.grid_mtf_strategy.entry_checker import EntryCheckResult
from action_resolver.grid_mtf_strategy.rearm_manager import RearmCheckResult
from action_processor.action_guard import GuardResult
from action_resolver.grid_mtf_strategy.partial_exit_bbw import BBWCheckDetails


class StatusLine:

    def build(
        self,
        price: float,
        check_result: EntryCheckResult | None = None,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_details: BBWCheckDetails | None = None,
        guard_result: GuardResult | None = None,
    ) -> Text:

        text = Text()
        text.append(f"PRICE: {price:.6f}  ", style="cyan")
        text.append(self._build_entry_status(check_result))
        text.append(self._build_exit_status(
            rearm_check_result,
            bbw_check_details,
        ))
        text.append(self._build_guard_status(guard_result))

        return text

    def _append_status_circle(self, text: Text, ok: bool) -> None:
        text.append(
            " ⬤ ",
            style="bold green" if ok else "bold red",
        )

    def _build_entry_status(
        self,
        check_result: EntryCheckResult | None = None,
    ) -> Text:

        text = Text()

        text.append("\nENTRY")

        self.append_ha_part(check_result, text)

        self.append_rsi_part(check_result, text)

        self.append_bb_part(check_result, text)

        return self.append_dist_part(check_result, text)

    def append_dist_part(self, check_result, text):
        text.append(" | DIST: ", style="cyan")
        if check_result is not None:
            distance = check_result.distance

            if distance.threshold is not None:
                text.append(
                    f"{distance.threshold:.6f}"
                )
                self._append_status_circle(text, distance.ok)
            else:
                text.append(
                    "N/A",
                    style="dim",
                )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        return text

    def append_bb_part(self, check_result, text):
        text.append(" | BB: ", style="cyan")
        if check_result is not None:
            bb = check_result.bb

            relation = (
                ">"
                if bb.value > bb.mid
                else "<"
                if bb.value < bb.mid
                else "="
            )
            text.append(
                f"({bb.tf}m) "
                f"(price:{bb.value:.6f} {relation} mid:{bb.mid:.6f})"
            )
            self._append_status_circle(text, bb.ok)
        else:
            text.append(
                "N/A",
                style="dim",
            )

    def append_rsi_part(self, check_result, text):
        text.append(" | RSI: ", style="cyan")
        if check_result is not None:
            rsi = check_result.rsi

            tf_th = (
                f"{rsi.threshold:.0f}"
                if rsi.threshold is not None
                else "N/A"
            )

            tf_v = (
                f"{rsi.value:.1f}"
                if rsi.value is not None
                else "N/A"
            )

            operator = ">" if rsi.value > rsi.threshold else "<"

            text.append(
                f"({rsi.tf}m) "
                f"cur:{tf_v} {operator} thres:{tf_th}"
            )
            self._append_status_circle(text, rsi.ok)
        else:
            text.append(
                "N/A",
                style="dim",
            )

    def append_ha_part(self, check_result, text):
        text.append(" | HA: ", style="cyan")
        if check_result is not None:
            ha = check_result.ha
            text.append(
                f"({ha.tf}m) [{ha.prev}→{ha.curr}]"
            )
            self._append_status_circle(text, ha.signal)
        else:
            text.append(
                "N/A",
                style="dim",
            )

    def _build_exit_status(
        self,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_details: BBWCheckDetails | None = None,
    ) -> Text:

        text = Text()

        text.append("\nEXIT  | RSI: ", style="cyan")
        if rearm_check_result is not None:
            text.append(
                f"({rearm_check_result.rsi:.1f}/"
                f"{rearm_check_result.rsi_threshold:.0f})"
            )
            self._append_status_circle(
                text,
                rearm_check_result.rsi_ok,
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | BBW: ", style="cyan")
        if bbw_check_details is not None:
            text.append(
                f"({bbw_check_details.tf}m) "
                f"[cross={bbw_check_details.bb_cross_tp:.6f} "
                f"width={bbw_check_details.bb_width_tp:.6f}]"
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        return text
    def _build_guard_status(
        self,
        guard_result: GuardResult | None = None,
    ) -> Text:

        text = Text()

        if guard_result is not None:
            text.append("\nGUARD: ", style="cyan")
            self._append_status_circle(text, guard_result.allowed)

        return text