import React, { useState, useEffect, useRef } from 'react';
import { Helmet } from 'react-helmet-async';
import { Send, ChevronDown, CheckCircle, AlertCircle } from 'lucide-react';
import { supabase } from '../lib/supabase';

export default function Contact() {
  const [isVisible, setIsVisible] = useState(false);
  const pageRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    if (pageRef.current) {
      observer.observe(pageRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: '',
    message: ''
  });
  const [submitStatus, setSubmitStatus] = useState(null); // 'success', 'error', or null
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    // Clear status when user starts typing again
    if (submitStatus) setSubmitStatus(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitStatus(null);

    try {
      const { error } = await supabase
        .from('contact_submissions')
        .insert([{
          name: formData.name,
          email: formData.email,
          subject: formData.subject || null,
          message: formData.message
        }]);

      if (error) throw error;

      setSubmitStatus('success');
      setFormData({ name: '', email: '', subject: '', message: '' });
    } catch (error) {
      console.error('Error submitting contact form:', error);
      setSubmitStatus('error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <Helmet>
        <title>Fusion First Testing</title>
        <meta name="description" content="Get in touch with the Fusion First team for questions, support, or feedback about our LLM quality testing platform." />
        <meta name="keywords" content="contact Fusion First, LLM testing support, chatbot testing help, AI testing feedback" />
        <meta property="og:title" content="Contact Us - Fusion First" />
        <meta property="og:description" content="Get in touch with the Fusion First team for questions, support, or feedback." />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/contact" />
      </Helmet>

      <div
        ref={pageRef}
        style={{
          padding: '4rem 1rem',
          opacity: isVisible ? 1 : 0,
          transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
          transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
        }}
      >
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
            <h1 style={{
              fontSize: 'clamp(1.875rem, 5vw, 2.5rem)',
              fontWeight: 'bold',
              color: 'white',
              marginBottom: '1rem'
            }}>
              Get in Touch
            </h1>
            <p style={{
              fontSize: '1.125rem',
              color: 'white',
              lineHeight: 1.6
            }}>
              Have a question or feedback? We would love to hear from you as we develop the tool further.
            </p>
          </div>

          {/* Contact Form */}
          <form
            onSubmit={handleSubmit}
            style={{
              background: 'rgba(80, 77, 154, 0.25)',
              border: '1px solid rgba(102, 196, 225, 0.2)',
              borderRadius: '1rem',
              padding: '2rem',
              backdropFilter: 'blur(10px)',
              transition: 'border-color 0.2s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {/* Name */}
              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  marginBottom: '0.5rem',
                  color: '#66c4e1'
                }}>
                  Name
                </label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    background: 'rgba(80, 77, 154, 0.4)',
                    border: '1px solid rgba(102, 196, 225, 0.3)',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontSize: '1rem',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Email */}
              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  marginBottom: '0.5rem',
                  color: '#66c4e1'
                }}>
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    background: 'rgba(80, 77, 154, 0.4)',
                    border: '1px solid rgba(102, 196, 225, 0.3)',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontSize: '1rem',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Subject */}
              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  marginBottom: '0.5rem',
                  color: '#66c4e1'
                }}>
                  Subject
                </label>
                <input
                  type="text"
                  name="subject"
                  value={formData.subject}
                  onChange={handleChange}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    background: 'rgba(80, 77, 154, 0.4)',
                    border: '1px solid rgba(102, 196, 225, 0.3)',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontSize: '1rem',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Message */}
              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  marginBottom: '0.5rem',
                  color: '#66c4e1'
                }}>
                  Message
                </label>
                <textarea
                  name="message"
                  value={formData.message}
                  onChange={handleChange}
                  required
                  rows={6}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    background: 'rgba(80, 77, 154, 0.4)',
                    border: '1px solid rgba(102, 196, 225, 0.3)',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontSize: '1rem',
                    resize: 'vertical',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Status Messages */}
              {submitStatus === 'success' && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '1rem',
                  background: 'rgba(102, 196, 225, 0.15)',
                  border: '1px solid rgba(102, 196, 225, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#66c4e1'
                }}>
                  <CheckCircle size={20} />
                  <span>Message sent successfully! We'll get back to you soon.</span>
                </div>
              )}

              {submitStatus === 'error' && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '1rem',
                  background: 'rgba(243, 143, 149, 0.15)',
                  border: '1px solid rgba(243, 143, 149, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#f38f95'
                }}>
                  <AlertCircle size={20} />
                  <span>Failed to send message. Please try again or email us directly at support-fusion@proton.me</span>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  width: '100%',
                  padding: '1rem',
                  background: isSubmitting
                    ? 'rgba(80, 77, 154, 0.5)'
                    : 'linear-gradient(to right, #f38f95, #db418b)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontWeight: 'bold',
                  fontSize: '1rem',
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  transition: 'transform 0.2s ease, background 0.2s ease',
                  opacity: isSubmitting ? 0.7 : 1
                }}
                onMouseEnter={(e) => {
                  if (!isSubmitting) e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                <Send size={20} />
                {isSubmitting ? 'Sending...' : 'Send Message'}
              </button>
            </div>
          </form>
        </div>

        {/* FAQ Section */}
        <FAQSection />
      </div>
    </>
  );
}

const faqItems = [
  {
    question: 'What type of system prompts work best with Fusion First?',
    answer: 'Fusion First works best with detailed system prompts that contain specific instructions, constraints, or domain knowledge. Complex prompts with multiple rules, boundaries, or expected behaviors are ideal candidates for quality testing. Short, simple prompts may not reveal as many potential issues.'
  },
  {
    question: 'How long does a quality scan take?',
    answer: 'A typical scan takes 1-3 minutes, and may take longer depending on the complexity of your system prompt. The tool generates 20 targeted test prompts, runs them against your configuration, and analyzes the responses for quality issues.'
  },
  {
    question: 'What do the severity levels mean?',
    answer: 'Critical issues are problems that could cause significant harm or completely break intended behavior. High severity issues are likely to cause user frustration or incorrect outputs. Medium issues may occasionally surface depending on user inputs. Low severity items are minor improvements or edge cases.'
  },
  {
    question: 'How do I use the AI-generated fixes?',
    answer: 'After running a scan, navigate to the Fixes tab to see AI-generated recommendations. Each fix includes specific text changes to add to your system prompt. You can copy the suggestions directly and integrate them into your prompt, then run another scan to verify the improvements.'
  },
  {
    question: 'Can I test prompts for any LLM provider?',
    answer: 'Yes! Fusion First tests the quality of your system prompt instructions, which are provider-agnostic. The issues detected (hallucinations, boundary violations, instruction failures) apply to any LLM including OpenAI, Anthropic, Google, and open-source models.'
  },
  {
    question: 'What happens when I run out of credits?',
    answer: 'When your credits are depleted, you can purchase additional scans through our pricing plans. The Starter plan includes 25 credits, Pro includes 75 credits, and Team includes 250 credits. All paid plans include priority support.'
  }
];

function FAQItem({ item, isOpen, onToggle }) {
  const contentRef = useRef(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    if (contentRef.current) {
      setHeight(contentRef.current.scrollHeight);
    }
  }, [item.answer]);

  return (
    <div
      style={{
        background: 'rgba(80, 77, 154, 0.25)',
        border: '1px solid rgba(102, 196, 225, 0.2)',
        borderRadius: '0.75rem',
        overflow: 'hidden',
        backdropFilter: 'blur(10px)',
        transition: 'border-color 0.2s'
      }}
      onMouseEnter={(e) => e.currentTarget.style.borderColor = '#66c4e1'}
      onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)'}
    >
      <button
        onClick={onToggle}
        style={{
          width: '100%',
          padding: '1.25rem',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          textAlign: 'left'
        }}
      >
        <span style={{
          fontSize: '1rem',
          fontWeight: '600',
          color: 'white'
        }}>
          {item.question}
        </span>
        <ChevronDown
          size={20}
          color="#66c4e1"
          style={{
            flexShrink: 0,
            transition: 'transform 0.3s ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)'
          }}
        />
      </button>
      <div
        style={{
          height: isOpen ? height : 0,
          overflow: 'hidden',
          transition: 'height 0.3s ease'
        }}
      >
        <div
          ref={contentRef}
          style={{
            padding: '0 1.25rem 1.25rem',
            color: 'white',
            lineHeight: 1.6,
            fontSize: '0.9375rem'
          }}
        >
          {item.answer}
        </div>
      </div>
    </div>
  );
}

function FAQSection() {
  const [openIndex, setOpenIndex] = useState(null);

  const toggleFAQ = (index) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '4rem auto 0', paddingBottom: '2rem' }}>
      <h2 style={{
        fontSize: 'clamp(1.5rem, 4vw, 2rem)',
        fontWeight: 'bold',
        color: 'white',
        textAlign: 'center',
        marginBottom: '2rem'
      }}>
        Frequently Asked Questions
      </h2>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {faqItems.map((item, index) => (
          <FAQItem
            key={index}
            item={item}
            isOpen={openIndex === index}
            onToggle={() => toggleFAQ(index)}
          />
        ))}
      </div>
    </div>
  );
}
