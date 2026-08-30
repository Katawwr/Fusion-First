import React, { useEffect, useState } from "react";
import { X, Mail, Loader, CheckCircle } from "lucide-react";
import { linkSubscriptionByEmail } from "../../lib/api";

export default function SignInModal({
  isOpen,
  onClose,
  onRequestMagicLink,
  loading,
  magicLinkSent,
  error,
  session,
  onCreditsLinked,
}) {
  const [email, setEmail] = useState("");
  const [marketingOptIn, setMarketingOptIn] = useState(false);
  const [linkEmail, setLinkEmail] = useState("");
  const [linkLoading, setLinkLoading] = useState(false);
  const [linkError, setLinkError] = useState("");
  const [linkSuccess, setLinkSuccess] = useState("");

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "unset";
    };
  }, [isOpen, onClose]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setEmail("");
      setMarketingOptIn(false);
      setLinkEmail("");
      setLinkError("");
      setLinkSuccess("");
    }
  }, [isOpen]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (email) {
      onRequestMagicLink(email, marketingOptIn);
    }
  };

  const handleLinkEmail = async (e) => {
    e.preventDefault();
    if (!linkEmail || !session) return;

    setLinkLoading(true);
    setLinkError("");
    setLinkSuccess("");

    try {
      const result = await linkSubscriptionByEmail(
        linkEmail,
        session.access_token,
      );
      if (result.success) {
        setLinkSuccess(
          `Linked! ${result.plan} plan with ${result.credits_remaining} credits.`,
        );
        if (onCreditsLinked) onCreditsLinked();
      } else {
        setLinkError(result.error || "No subscription found for this email.");
      }
    } catch (err) {
      setLinkError("Failed to link subscription. Please try again.");
    } finally {
      setLinkLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(102, 196, 225, 0.3)",
          backdropFilter: "blur(8px)",
        }}
      />

      {/* Modal */}
      <div
        style={{
          position: "relative",
          background: "linear-gradient(135deg, #66c4e1 0%, #4a9db8 100%)",
          border: "1px solid rgba(255, 255, 255, 0.3)",
          borderRadius: "1rem",
          padding: "2rem",
          maxWidth: "400px",
          width: "100%",
          boxShadow: "0 25px 50px rgba(0, 0, 0, 0.5)",
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "1rem",
            right: "1rem",
            background: "none",
            border: "none",
            color: "rgba(255, 255, 255, 0.8)",
            cursor: "pointer",
            padding: "0.25rem",
          }}
        >
          <X size={20} />
        </button>

        {/* Content */}
        <div style={{ textAlign: "center" }}>
          <h2
            style={{
              fontSize: "1.5rem",
              fontWeight: "bold",
              color: "white",
              marginBottom: "0.5rem",
            }}
          >
            Sign In
          </h2>

          {/* Show success state if magic link was sent and not signed in yet */}
          {magicLinkSent && !session ? (
            <div style={{ marginTop: "1.5rem" }}>
              <CheckCircle
                size={48}
                color="#f38f95"
                style={{ margin: "0 auto 1rem" }}
              />
              <p
                style={{
                  color: "white",
                  fontSize: "1rem",
                  marginBottom: "0.5rem",
                }}
              >
                Check your email!
              </p>
              <p
                style={{
                  color: "rgba(255, 255, 255, 0.9)",
                  fontSize: "0.875rem",
                }}
              >
                We sent a link to <strong>{email}</strong>
              </p>
              <p
                style={{
                  color: "rgba(255, 255, 255, 0.7)",
                  fontSize: "0.75rem",
                  marginTop: "1rem",
                }}
              >
                The link expires in 15 minutes.
              </p>
            </div>
          ) : !session ? (
            // Email input form (when not signed in)
            <>
              <p
                style={{
                  color: "rgba(255, 255, 255, 0.9)",
                  fontSize: "0.9rem",
                  marginBottom: "1.5rem",
                }}
              >
                Enter your email to receive a one time link.
              </p>

              <form onSubmit={handleSubmit}>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  autoComplete="email"
                  style={{
                    width: "100%",
                    padding: "0.75rem 1rem",
                    borderRadius: "0.5rem",
                    border: "1px solid rgba(255, 255, 255, 0.3)",
                    background: "rgba(255, 255, 255, 0.1)",
                    color: "white",
                    fontSize: "1rem",
                    marginBottom: "1rem",
                    outline: "none",
                  }}
                />

                {/* Marketing opt-in checkbox */}
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    marginBottom: "1rem",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={marketingOptIn}
                    onChange={(e) => setMarketingOptIn(e.target.checked)}
                    style={{
                      width: "1rem",
                      height: "1rem",
                      accentColor: "#f38f95",
                    }}
                  />
                  <span
                    style={{
                      color: "rgba(255, 255, 255, 0.85)",
                      fontSize: "0.75rem",
                    }}
                  >
                    Send me product updates and marketing emails
                  </span>
                </label>

                <button
                  type="submit"
                  disabled={loading || !email}
                  style={{
                    width: "100%",
                    padding: "0.75rem 1.5rem",
                    background: "white",
                    border: "none",
                    borderRadius: "0.5rem",
                    color: "#1f2937",
                    fontWeight: "600",
                    fontSize: "0.9375rem",
                    cursor: loading || !email ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.75rem",
                    opacity: loading || !email ? 0.7 : 1,
                  }}
                >
                  {loading && <Loader size={18} className="animate-spin" />}
                  {loading ? "Sending..." : "Send Link"}
                </button>

                {/* Error display */}
                {error && (
                  <p
                    style={{
                      color: "#fee2e2",
                      fontSize: "0.8rem",
                      marginTop: "0.75rem",
                      padding: "0.5rem",
                      background: "rgba(239, 68, 68, 0.2)",
                      borderRadius: "0.375rem",
                    }}
                  >
                    {error}
                  </p>
                )}
              </form>
            </>
          ) : (
            // Signed in - show subscription linking section
            <p
              style={{
                color: "rgba(255, 255, 255, 0.9)",
                fontSize: "0.9rem",
                marginBottom: "0.5rem",
              }}
            >
              You're signed in as {session.user?.email}
            </p>
          )}

          {/* Manual email link section - only show when signed in */}
          {session && (
            <div
              style={{
                marginTop: "1.5rem",
                borderTop: "1px solid rgba(255, 255, 255, 0.2)",
                paddingTop: "1.5rem",
              }}
            >
              <p
                style={{
                  color: "rgba(255, 255, 255, 0.9)",
                  fontSize: "0.8rem",
                  marginBottom: "0.75rem",
                }}
              >
                Purchased with a different email?
              </p>
              <form
                onSubmit={handleLinkEmail}
                style={{ display: "flex", gap: "0.5rem" }}
              >
                <input
                  type="email"
                  value={linkEmail}
                  onChange={(e) => setLinkEmail(e.target.value)}
                  placeholder="Purchase email address"
                  style={{
                    flex: 1,
                    padding: "0.5rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid rgba(255, 255, 255, 0.3)",
                    background: "rgba(255, 255, 255, 0.1)",
                    color: "white",
                    fontSize: "0.875rem",
                    outline: "none",
                  }}
                />
                <button
                  type="submit"
                  disabled={linkLoading || !linkEmail}
                  style={{
                    padding: "0.5rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "none",
                    background: "rgba(255, 255, 255, 0.2)",
                    color: "white",
                    cursor:
                      linkLoading || !linkEmail ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.25rem",
                  }}
                >
                  {linkLoading ? (
                    <Loader size={16} className="animate-spin" />
                  ) : (
                    <Mail size={16} />
                  )}
                </button>
              </form>
              {linkError && (
                <p
                  style={{
                    color: "#fee2e2",
                    fontSize: "0.75rem",
                    marginTop: "0.5rem",
                  }}
                >
                  {linkError}
                </p>
              )}
              {linkSuccess && (
                <p
                  style={{
                    color: "#d1fae5",
                    fontSize: "0.75rem",
                    marginTop: "0.5rem",
                  }}
                >
                  {linkSuccess}
                </p>
              )}
            </div>
          )}

          <p
            style={{
              marginTop: "1.5rem",
              fontSize: "0.65rem",
              color: "rgba(255, 255, 255, 0.5)",
            }}
          >
            By signing in, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
