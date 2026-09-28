let uploadId = null;
let attachments = [];
let campaignId = null;

const $ = (id) => document.getElementById(id);

$("contacts").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("contacts", file);
  $("upload_stats").textContent = "Reading file…";
  const res = await fetch("/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (data.error) {
    $("upload_stats").innerHTML = `<span class="bad">${data.error}</span>`;
    $("btn_start").disabled = true;
    return;
  }
  uploadId = data.upload_id;
  const s = data.stats;
  $("upload_stats").innerHTML =
    `<span class="ok">✓ ${s.valid} valid emails</span> &nbsp; ` +
    (s.duplicates ? `<span class="bad">✓ ${s.duplicates} duplicates removed</span> &nbsp;` : "") +
    (s.invalid ? `<span class="bad">✓ ${s.invalid} invalid removed</span>` : "") +
    `<br><span style="color:#6b7280">Detected email column: "${s.email_column_used}"</span>`;
  checkReady();
});

$("attachment_input").addEventListener("change", async (e) => {
  for (const file of e.target.files) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/upload-attachment", { method: "POST", body: fd });
    const data = await res.json();
    if (data.path) {
      attachments.push(data.path);
      const li = document.createElement("li");
      li.textContent = data.name;
      $("attachment_list").appendChild(li);
    }
  }
});

function checkReady() {
  const ready = uploadId && $("sender_email").value && $("app_password").value &&
                $("subject").value && $("body").value;
  $("btn_start").disabled = !ready;
}
["sender_email", "app_password", "subject", "body"].forEach(id =>
  $(id).addEventListener("input", checkReady)
);

$("btn_test").addEventListener("click", async () => {
  $("setup_error").textContent = "";
  if (!$("sender_email").value || !$("app_password").value || !$("subject").value || !$("body").value) {
    $("setup_error").textContent = "Fill in sender email, app password, subject and body first.";
    return;
  }
  $("btn_test").textContent = "Sending test…";
  const res = await fetch("/test-email", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sender_email: $("sender_email").value, app_password: $("app_password").value,
      subject: $("subject").value, body: $("body").value, attachments,
    }),
  });
  const data = await res.json();
  $("btn_test").textContent = "Send Test Email to Myself";
  if (data.ok) alert("Test email sent to " + $("sender_email").value);
  else $("setup_error").textContent = "Test send failed: " + data.error;
});

$("btn_start").addEventListener("click", async () => {
  const res = await fetch("/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: uploadId, sender_email: $("sender_email").value,
      app_password: $("app_password").value, subject: $("subject").value,
      body: $("body").value, attachments,
      delay_min: $("delay_min").value, delay_max: $("delay_max").value,
      daily_cap: $("daily_cap").value,
    }),
  });
  const data = await res.json();
  if (data.error) { $("setup_error").textContent = data.error; return; }
  campaignId = data.campaign_id;
  $("total_count").textContent = data.total;
  $("setup").classList.add("hidden");
  $("sending").classList.remove("hidden");
  listen();
});

function listen() {
  const src = new EventSource(`/stream/${campaignId}`);
  src.onmessage = (e) => {
    const div = document.createElement("div");
    if (e.data.startsWith("FATAL") || e.data.includes("FAILED")) div.className = "fail";
    div.textContent = e.data;
    $("log").appendChild(div);
    $("log").scrollTop = $("log").scrollHeight;
  };
  src.addEventListener("counts", (e) => {
    const c = JSON.parse(e.data);
    $("sent_count").textContent = c.sent;
    $("failed_count").textContent = c.failed;
    const pct = c.total ? Math.round(((c.sent + c.failed) / c.total) * 100) : 0;
    $("progress_fill").style.width = pct + "%";
  });
  src.addEventListener("done", () => {
    src.close();
    $("btn_report").href = `/report/${campaignId}`;
    $("btn_report").classList.remove("hidden");
  });
}

$("btn_pause").addEventListener("click", async () => {
  await fetch(`/pause/${campaignId}`, { method: "POST" });
  $("btn_pause").classList.add("hidden");
  $("btn_resume").classList.remove("hidden");
});
$("btn_resume").addEventListener("click", async () => {
  await fetch(`/resume/${campaignId}`, { method: "POST" });
  $("btn_resume").classList.add("hidden");
  $("btn_pause").classList.remove("hidden");
});
$("btn_stop").addEventListener("click", async () => {
  if (!confirm("Stop sending? Already-sent emails cannot be undone, but no more will go out.")) return;
  await fetch(`/stop/${campaignId}`, { method: "POST" });
});
