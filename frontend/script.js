const ws = new WebSocket(`ws://${location.host}/ws`);
const video = document.getElementById("avatarVideo");
const stillImage = document.getElementById("stillImage");
const statusEl = document.getElementById("status");
const messagesDiv = document.getElementById("messages");
const form = document.getElementById("chatForm");
const input = document.getElementById("userInput");

let isPlaying = false;

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "welcome") {
    playVideo(data.video_url);
    statusEl.textContent = "Welcome!";
  }

  if (data.type === "status") {
    statusEl.textContent = data.message;
    showStillImage(data.image);
  }

  if (data.type === "text_response") {
    addMessage(data.message, "bot");
  }

  if (data.type === "video_ready") {
    statusEl.textContent = "";
    playVideo(data.video_url);
    addMessage(data.message, "bot");
  }

  if (data.type === "error") {
    statusEl.textContent = "Error";
    addMessage("Sorry, something went wrong.", "bot");
  }
};

form.onsubmit = (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;
  addMessage(msg, "user");
  ws.send(JSON.stringify({ message: msg }));
  input.value = "";
};

function playVideo(src) {
  if (isPlaying) video.pause();
  video.src = src;
  video.style.display = "block";
  stillImage.style.display = "none";
  video.play().catch(() => {});
  isPlaying = true;

  video.onended = () => {
    isPlaying = false;
    showStillImage("/static/loading-avatar.png");
  };
}

function showStillImage(src) {
  video.pause();
  video.style.display = "none";
  stillImage.src = src;
  stillImage.style.display = "block";
}

function addMessage(text, sender) {
  const p = document.createElement("p");
  p.textContent = text;
  p.className = sender;
  messagesDiv.appendChild(p);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Initial still image
showStillImage("/static/loading-avatar.png");