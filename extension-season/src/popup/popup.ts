// Popup: feed freshness and the one setting there is.

function send<T>(message: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!response?.ok) return reject(new Error(response?.error ?? "no response"));
      resolve(response as T);
    });
  });
}

function set(id: string, value: string): void {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

async function refreshStatus(): Promise<void> {
  try {
    const { status } = await send<{ status: { state: string; season?: string; generatedAt?: string; fetchedAt?: string; error?: string } }>({
      type: "GET_FEED_STATUS",
    });
    set("state", status.error ?? status.state);
    set("season", status.season ?? "–");
    set("generated", status.generatedAt ? new Date(status.generatedAt).toLocaleString() : "–");
    set("fetched", status.fetchedAt ? new Date(status.fetchedAt).toLocaleString() : "–");
  } catch (error) {
    set("state", error instanceof Error ? error.message : String(error));
  }

  const { url } = await send<{ url: string }>({ type: "GET_BASE_URL" });
  const input = document.getElementById("base") as HTMLInputElement | null;
  if (input) input.value = url;
}

document.getElementById("refresh")?.addEventListener("click", async () => {
  set("state", "downloading…");
  try {
    await send({ type: "GET_FEED", force: true });
  } catch (error) {
    set("state", error instanceof Error ? error.message : String(error));
    return;
  }
  await refreshStatus();
});

document.getElementById("save")?.addEventListener("click", async () => {
  const input = document.getElementById("base") as HTMLInputElement | null;
  if (!input) return;
  await send({ type: "SET_BASE_URL", url: input.value.trim() });
  set("state", "saved — refreshing");
  await send({ type: "GET_FEED", force: true }).catch(() => undefined);
  await refreshStatus();
});

void refreshStatus();
