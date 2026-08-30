import { API_URL } from "./constants";

// Always use direct API URL (CORS is enabled on backend)
const BASE_URL = API_URL;

// Health check to wake up the Modal backend (cold start can take 10-30 seconds)
export async function wakeBackend() {
  try {
    console.log("[API] Waking up backend at:", BASE_URL);
    const response = await fetch(`${BASE_URL}/api/health`, {
      method: "GET",
    });
    if (response.ok) {
      console.log("[API] Backend is awake");
      return true;
    }
  } catch (error) {
    console.log(
      "[API] Backend wake-up ping failed (may be cold starting):",
      error.message,
    );
  }
  return false;
}

// Fetch free credits based on fingerprint
export async function fetchFreeCredits() {
  try {
    console.log("[API] Fetching credits from:", `${BASE_URL}/api/credits`);
    const response = await fetch(`${BASE_URL}/api/credits`, {
      method: "GET",
    });

    if (!response.ok) {
      console.error(
        "[API] Credits fetch failed:",
        response.status,
        response.statusText,
      );
      throw new Error("Failed to fetch credits");
    }

    const data = await response.json();
    console.log("[API] Credits received:", data);
    return data;
  } catch (error) {
    console.error("[API] fetchFreeCredits error:", error);
    // Return default credits on error to allow tool usage
    return { remaining_credits: 2, total_credits: 2 };
  }
}

// Fetch license credits
export async function fetchLicenseCredits(licenseKey) {
  const response = await fetch(
    `${BASE_URL}/api/license/credits?license_key=${encodeURIComponent(licenseKey)}`,
    {
      method: "GET",
    },
  );

  if (!response.ok) {
    throw new Error("Failed to fetch license credits");
  }

  return response.json();
}

// Create a new API key
export async function createApiKey(accessToken, name = "Default") {
  const response = await fetch(`${BASE_URL}/api/keys`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  if (!response.ok) throw new Error("Failed to create API key");
  return response.json();
}

// List API keys for authenticated user
export async function listApiKeys(accessToken) {
  const response = await fetch(`${BASE_URL}/api/keys`, {
    method: "GET",
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) throw new Error("Failed to list API keys");
  return response.json();
}

// Revoke an API key
export async function revokeApiKey(accessToken, keyId) {
  const response = await fetch(
    `${BASE_URL}/api/keys/${encodeURIComponent(keyId)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );

  if (!response.ok) throw new Error("Failed to revoke API key");
  return response.json();
}

// Validate license key
export async function validateLicenseKey(licenseKey) {
  const response = await fetch(`${BASE_URL}/api/license/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ license_key: licenseKey }),
  });

  return response.json();
}

// Fetch credits for authenticated Supabase user
export async function fetchUserCredits(accessToken) {
  console.log(
    "[API] fetchUserCredits called with token:",
    accessToken ? `${accessToken.substring(0, 20)}...` : "NONE",
  );

  if (!accessToken) {
    throw new Error("No access token provided");
  }

  const response = await fetch(`${BASE_URL}/api/user/credits`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  console.log("[API] fetchUserCredits response status:", response.status);

  if (!response.ok) {
    const errorText = await response.text();
    console.error("[API] fetchUserCredits error:", errorText);
    throw new Error("Failed to fetch user credits");
  }

  return response.json();
}

// Link a license key to authenticated user
export async function linkLicenseToUser(accessToken, licenseKey) {
  const response = await fetch(`${BASE_URL}/api/user/link-license`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ license_key: licenseKey }),
  });

  return response.json();
}

// Link subscription by purchase email (for users who purchased with different email)
export async function linkSubscriptionByEmail(purchaseEmail, accessToken) {
  try {
    const response = await fetch(`${BASE_URL}/api/user/link-subscription`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ purchase_email: purchaseEmail }),
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        error: data.detail || "Failed to link subscription",
      };
    }

    return { success: true, ...data };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Fetch scan history for authenticated user
export async function fetchScanHistory(accessToken, offset = 0, limit = 20) {
  const response = await fetch(
    `${BASE_URL}/api/user/scans?offset=${offset}&limit=${limit}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );

  if (!response.ok) {
    throw new Error("Failed to fetch scan history");
  }

  return response.json();
}

// Fetch full scan detail by ID
export async function fetchScanDetail(accessToken, scanId) {
  const response = await fetch(
    `${BASE_URL}/api/user/scans/${encodeURIComponent(scanId)}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );

  if (!response.ok) {
    if (response.status === 404) throw new Error("Scan not found");
    throw new Error("Failed to fetch scan detail");
  }

  return response.json();
}

// Run quality scan with SSE streaming, results arrive one at a time
export async function runQualityScanStreaming(
  systemPrompt,
  licenseKey = "",
  options = {},
) {
  const {
    accessToken = null,
    onTestResult,
    onStatus,
    onFixes,
    onSummary,
    onComplete,
    onError,
  } = options;

  await wakeBackend();

  const headers = { "Content-Type": "application/json" };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetch(`${BASE_URL}/api/scan/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      system_prompt: systemPrompt,
      num_tests: 20,
      license_key: licenseKey || "",
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Server error: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop(); // keep incomplete line in buffer

    let currentEvent = null;
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ") && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          switch (currentEvent) {
            case "test_result":
              onTestResult?.(data);
              break;
            case "status":
              onStatus?.(data);
              break;
            case "fixes":
              onFixes?.(data);
              break;
            case "summary":
              onSummary?.(data);
              break;
            case "complete":
              onComplete?.(data);
              break;
            case "error":
              onError?.(data);
              break;
          }
        } catch (e) {
          console.warn("[SSE] Failed to parse event data:", e);
        }
        currentEvent = null;
      }
    }
  }
}

// Run quality scan with retry logic (non-streaming, kept for API/CI use)
export async function runQualityScan(
  systemPrompt,
  licenseKey = "",
  options = {},
) {
  const { maxRetries = 3, accessToken = null } = options;
  let lastError = null;

  console.log("[API] Starting scan request to:", `${BASE_URL}/api/scan`);
  console.log("[API] System prompt length:", systemPrompt.length);
  console.log("[API] License key provided:", !!licenseKey);
  console.log("[API] Auth token provided:", !!accessToken);

  // Try to wake up the backend first (handles cold starts)
  await wakeBackend();

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`[API] Scan attempt ${attempt}/${maxRetries}`);

      // Create abort controller with 5-minute timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => {
          console.log("[API] Request timeout triggered");
          controller.abort();
        },
        5 * 60 * 1000,
      );

      const requestBody = {
        system_prompt: systemPrompt,
        num_tests: 20,
        license_key: licenseKey || "",
      };

      // Build headers - include auth token if available (for email-based greenlist)
      const headers = {
        "Content-Type": "application/json",
      };
      if (accessToken) {
        headers["Authorization"] = `Bearer ${accessToken}`;
      }

      console.log(
        "[API] Sending request with body:",
        JSON.stringify(requestBody).substring(0, 200) + "...",
      );

      const response = await fetch(`${BASE_URL}/api/scan`, {
        method: "POST",
        headers,
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      console.log("[API] Scan response received - status:", response.status);

      // Handle specific HTTP errors
      if (response.status === 503) {
        console.log("[API] Server returned 503 (busy)");
        if (attempt < maxRetries) {
          console.log(
            `[API] Server busy, retrying in ${attempt * 5} seconds...`,
          );
          await new Promise((r) => setTimeout(r, attempt * 5000));
          continue;
        }
        throw new Error(
          "Server is experiencing high load. Please try again in a few minutes.",
        );
      }

      if (response.status === 429) {
        const errorData = await response.json().catch(() => ({}));
        console.log("[API] Rate limited:", errorData);
        throw new Error(
          errorData.detail ||
            "Rate limit exceeded. Please wait before trying again.",
        );
      }

      if (!response.ok) {
        const errorText = await response.text();
        console.error("[API] Scan error response:", response.status, errorText);
        throw new Error(errorText || `Server error: ${response.status}`);
      }

      const data = await response.json();
      console.log("[API] Scan completed successfully, results:", data.success);

      if (!data.success) {
        const errorMsg = data.error || "Scan failed";
        console.log("[API] Scan returned success:false -", errorMsg);
        if (
          errorMsg.includes("timeout") ||
          errorMsg.includes("rate") ||
          errorMsg.includes("busy")
        ) {
          if (attempt < maxRetries) {
            console.log(`[API] Retryable error, attempt ${attempt + 1}...`);
            await new Promise((r) => setTimeout(r, attempt * 3000));
            continue;
          }
        }
        throw new Error(errorMsg);
      }

      return data;
    } catch (error) {
      lastError = error;
      console.error(
        `[API] Scan attempt ${attempt} failed:`,
        error.name,
        error.message,
      );

      if (error.name === "AbortError") {
        console.log("[API] Request was aborted (timeout)");
        if (attempt < maxRetries) {
          console.log(
            `[API] Retrying after timeout (attempt ${attempt + 1})...`,
          );
          continue;
        }
        lastError = new Error(
          "Request timed out. The server may be busy. Please try again.",
        );
      } else if (
        error.message.includes("Failed to fetch") ||
        error.message.includes("NetworkError") ||
        error.message.includes("network")
      ) {
        console.log("[API] Network error detected");
        if (attempt < maxRetries) {
          console.log(
            `[API] Network error, retrying in ${attempt * 3} seconds...`,
          );
          await new Promise((r) => setTimeout(r, attempt * 3000));
          await wakeBackend();
          continue;
        }
        lastError = new Error(
          "Unable to connect to server. Please check your connection and try again.",
        );
      }

      // Don't retry non-retryable errors
      if (
        error.message.includes("Rate limit") ||
        error.message.includes("credits") ||
        error.message.includes("No credits")
      ) {
        console.log("[API] Non-retryable error, stopping");
        break;
      }
    }
  }

  console.error(
    "[API] All attempts failed, throwing error:",
    lastError?.message,
  );
  throw lastError || new Error("Unknown error occurred");
}
