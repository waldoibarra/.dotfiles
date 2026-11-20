# Spawn and close a worker

Back to [agent coordination](README.md). Write the [brief](briefing.md) first.

Use this when the operator asks to spawn a worker, an independent reviewer, or a peer agent.
Say "spawn a worker" or "spawn an independent reviewer"; add "with Astra" or "with Claude" to pick
the harness. Without a harness, use Pi, because a different model gives a more independent read.

**One workspace per task, one tab per worker inside it, one pane per tab.** Workers on the same
issue or change share the task's workspace; a worker on a different task gets its own. The
workspace answers "what task", the tab "what role", the pane "who" ([layer rules](naming.md#label-the-layers)).
Split the lead's tab only when the operator says "split", "beside me", or "in this tab".
Learned on 2026-11-02: three workers on one issue were spawned in three workspaces, and the
operator asked for one shared workspace.

Label the workspace, tab, and pane by the [layer rules](naming.md#label-the-layers).

1. Resolve the lead's own pane and name with `herdr agent list`.
2. Write the [brief](briefing.md) to a file before starting the worker.
3. For the task's first worker, create the workspace without taking focus, passing the worker's
  directory and the task label. For every later worker on the same task, create a tab in that
  workspace instead, with the worker's directory and the role as label. Either result's
  `root_pane.pane_id` and `tab.tab_id` are the new pane and tab.
4. Rename the tab to the role and the pane to the worker's name. The name follows the
  [naming rules](naming.md) and keeps the model suffix: `roy-92-sonnet-docs`, not `roy-92-w3`.
  Pass each id as its own argument; a loop that word-splits one variable renames nothing.
5. Pass the brief through the harness startup arguments in the newly created worker pane.
    Use one shell-safe argument naming the mission and brief. Never submit it to an existing editor.
6. Inspect startup failures before retrying: a timeout can leave the intended worker running.
7. Verify the agreed output artifact. Do not send a reminder to the worker or the lead.
8. Close the worker's tab once its deliverable is verified, and the workspace when its last tab
  closes, unless the operator asked to keep them. Close only containers this lead created.
  Closing ends the agent; say so in the reply.

```sh
herdr workspace create --cwd <dir> --label "<Task label>" --no-focus                 # step 3, first worker
herdr tab create --workspace <ws-id> --cwd <dir> --label "<Role>"                    # step 3, later workers
herdr tab rename <new-tab-id> "<Role>"                                               # step 4
herdr pane rename <new-pane-id> <name>
herdr agent start <name> --kind pi --pane <new-pane-id> -- --model <model> 'Review the plan in <brief>'
herdr workspace close <new-workspace-id>                                             # step 8
```

On request, replace steps 3 and 4 with a split of the lead's pane; `pane.pane_id` is the new pane:

```sh
herdr pane split <lead-pane-id> --direction right --ratio 0.5 --cwd <dir> --no-focus
herdr pane close <new-pane-id>   # when finished
```

Workspace, tab, and pane creation, renames, and closes were exercised on 2026-11-01; tab creation
inside a shared workspace and the trust-dialog answer on 2026-11-02.
Starting an agent and sending prompts keep their usual approval boundaries.
