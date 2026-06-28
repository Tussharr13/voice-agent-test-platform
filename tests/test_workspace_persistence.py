import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspacePersistenceTests(unittest.TestCase):
    def test_workspace_state_is_sanitized_read_and_written(self):
        script = textwrap.dedent(
            """
            import {
              WORKSPACE_STATE_KEY,
              readWorkspaceState,
              sanitizeWorkspaceState,
              writeWorkspaceState,
            } from "./static/workspacePersistence.mjs";

            const invalid = sanitizeWorkspaceState({
              activeTab: "voice",
              activeProjectId: 22,
              activeChatId: "chat_1",
              activeDocsChatId: null,
              extra: "ignored",
            });
            if (JSON.stringify(invalid) !== JSON.stringify({
              activeTab: "analyzer",
              activeProjectId: "",
              activeChatId: "chat_1",
              activeDocsChatId: "",
            })) {
              throw new Error(`unexpected sanitized state ${JSON.stringify(invalid)}`);
            }

            const storage = {
              value: "{bad json",
              getItem(key) { return key === WORKSPACE_STATE_KEY ? this.value : null; },
              setItem(key, value) { this.key = key; this.value = value; },
            };
            const fallback = readWorkspaceState(storage);
            if (fallback.activeTab !== "analyzer" || fallback.activeProjectId !== "") {
              throw new Error(`unexpected fallback ${JSON.stringify(fallback)}`);
            }

            const hashState = readWorkspaceState(storage, { hash: "#tab=docs&project=project_hash&chat=chat_hash&docs=docs_hash" });
            if (hashState.activeTab !== "docs" || hashState.activeProjectId !== "project_hash" || hashState.activeDocsChatId !== "docs_hash") {
              throw new Error(`unexpected hash state ${JSON.stringify(hashState)}`);
            }

            const locationLike = { pathname: "/workbench", search: "?v=1", hash: "" };
            const historyLike = {
              replaceState(_state, _title, url) {
                this.url = url;
              },
            };
            const written = writeWorkspaceState({
              activeTab: "testing",
              activeProjectId: "project_1",
              activeChatId: "chat_2",
              activeDocsChatId: "docs_3",
              noisy: true,
            }, storage, historyLike, locationLike);
            const persisted = JSON.parse(storage.value);
            if (storage.key !== WORKSPACE_STATE_KEY) throw new Error("wrong storage key");
            if (JSON.stringify(written) !== JSON.stringify(persisted)) {
              throw new Error("write return did not match persisted payload");
            }
            if (persisted.activeTab !== "testing" || persisted.activeProjectId !== "project_1") {
              throw new Error(`unexpected persisted state ${JSON.stringify(persisted)}`);
            }
            if ("noisy" in persisted) throw new Error("persisted noisy field");
            if (historyLike.url !== "/workbench?v=1#tab=testing&project=project_1&chat=chat_2&docs=docs_3") {
              throw new Error(`unexpected hash url ${historyLike.url}`);
            }
            """
        )

        subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
