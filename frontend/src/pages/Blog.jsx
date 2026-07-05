import React, { useEffect, useRef, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router-dom';
import { Calendar, Clock, ArrowRight } from 'lucide-react';

// Article metadata
const articles = [
  {
    slug: 'enterprise-chatbots-2026',
    title: 'The State of Enterprise Chatbots in 2026: Challenges, Trends, and Best Practices',
    description: 'A comprehensive research-based analysis of enterprise chatbot adoption.',
    date: '2026-01-28',
    readTime: '25 min',
    tags: ['Enterprise', 'Research', 'Trends'],
  },
  {
    slug: 'chatbot-testing-checklist',
    title: '5 Signs Your Chatbot Needs Quality Testing',
    description: 'A quick checklist to identify when your AI chatbot requires immediate quality testing and validation.',
    date: '2026-01-22',
    readTime: '3 min',
    tags: ['Checklist', 'Quick Guide', 'Testing'],
  },
  {
    slug: 'hallucination-quick-facts',
    title: '7 Quick Facts About LLM Hallucinations',
    description: 'Essential facts every developer should know about AI hallucinations and how to address them.',
    date: '2026-01-18',
    readTime: '4 min',
    tags: ['Hallucination', 'Quick Facts', 'AI Safety'],
  },
  {
    slug: 'llm-quality-testing-guide',
    title: 'Why LLM Quality Testing Matters for Production',
    description: 'Learn why automated quality testing is essential before deploying LLM-powered applications to production environments.',
    date: '2026-01-15',
    readTime: '12 min',
    tags: ['LLM', 'Testing', 'Production'],
  },
  {
    slug: 'preventing-hallucinations',
    title: 'Preventing Hallucinations in AI Chatbots',
    description: 'Discover strategies and techniques to reduce hallucinations in your AI chatbot and improve response accuracy.',
    date: '2026-01-10',
    readTime: '10 min',
    tags: ['Hallucination', 'AI Safety', 'Best Practices'],
  },
  {
    slug: 'system-prompt-best-practices',
    title: 'System Prompt Best Practices Guide',
    description: 'A comprehensive guide to writing effective system prompts that produce consistent, high-quality LLM outputs.',
    date: '2026-01-05',
    readTime: '15 min',
    tags: ['System Prompts', 'Guide', 'Best Practices'],
  },
];

function ArticleCard({ article, index }) {
  return (
    <Link to={`/blog/${article.slug}`} style={{ textDecoration: 'none' }}>
      <div
        style={{
          height: '100%',
          padding: '1.5rem',
          background: 'rgba(80, 77, 154, 0.25)',
          border: '1px solid rgba(102, 196, 225, 0.2)',
          borderRadius: '1rem',
          backdropFilter: 'blur(10px)',
          cursor: 'pointer',
          transition: 'border-color 0.2s ease, transform 0.2s ease'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#66c4e1';
          e.currentTarget.style.transform = 'translateY(-3px)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
          e.currentTarget.style.transform = 'translateY(0)';
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* Tags */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
            {article.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.75rem',
                  background: 'rgba(80, 77, 154, 0.4)',
                  color: '#66c4e1',
                  borderRadius: '9999px'
                }}
              >
                {tag}
              </span>
            ))}
          </div>

          {/* Title */}
          <h2 style={{
            fontSize: '1.25rem',
            fontWeight: 'bold',
            color: 'white',
            marginBottom: '0.5rem'
          }}>
            {article.title}
          </h2>

          {/* Description */}
          <p style={{
            color: 'white',
            fontSize: '0.875rem',
            marginBottom: '1rem',
            flex: 1,
            lineHeight: 1.6
          }}>
            {article.description}
          </p>

          {/* Meta */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.75rem',
            color: 'white'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Calendar size={12} />
                {new Date(article.date).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#f38f95' }}>
                <Clock size={12} color="#f38f95" />
                {article.readTime}
              </span>
            </div>
            <ArrowRight size={16} color="#66c4e1" />
          </div>
        </div>
      </div>
    </Link>
  );
}

export default function Blog() {
  const [isVisible, setIsVisible] = useState(false);
  const [displayCount, setDisplayCount] = useState(6);
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

  // Sort articles chronologically (newest first)
  const sortedArticles = [...articles].sort((a, b) => new Date(b.date) - new Date(a.date));
  const displayedArticles = sortedArticles.slice(0, displayCount);
  const hasMore = displayCount < sortedArticles.length;

  const loadMore = () => {
    setDisplayCount(prev => Math.min(prev + 6, sortedArticles.length));
  };

  return (
    <>
      <Helmet>
        <title>Fusion First Testing</title>
        <meta
          name="description"
          content="Expert articles on LLM quality testing, preventing AI hallucinations, system prompt engineering, and enterprise chatbot best practices. Free guides and research."
        />
        <meta name="keywords" content="LLM testing, chatbot quality, AI hallucinations, system prompts, enterprise chatbots, AI safety, prompt engineering" />
        <meta property="og:title" content="LLM Quality Testing Blog | Fusion First" />
        <meta property="og:description" content="Expert articles on LLM quality testing, preventing AI hallucinations, and chatbot best practices." />
        <meta property="og:type" content="website" />
        <link rel="canonical" href="https://fusion-first-testing.com/blog" />
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
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
            <h1 style={{
              fontSize: 'clamp(1.875rem, 5vw, 2.5rem)',
              fontWeight: 'bold',
              color: 'white',
              marginBottom: '1rem'
            }}>
              All About Chatbots
            </h1>
            <p style={{
              fontSize: '1.25rem',
              color: 'white',
              maxWidth: '600px',
              margin: '0 auto',
              lineHeight: 1.6
            }}>
              Learn best practices for LLM quality testing, system prompt design,
              and building reliable AI applications.
            </p>
          </div>

          {/* Articles Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.5rem'
          }}>
            {displayedArticles.map((article, index) => (
              <ArticleCard key={article.slug} article={article} index={index} />
            ))}
          </div>

          {/* More Button */}
          {hasMore && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '2rem' }}>
              <button
                onClick={loadMore}
                style={{
                  padding: '0.875rem 1.5rem',
                  background: 'linear-gradient(to right, #f38f95, #db418b)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: 'white',
                  fontWeight: 'bold',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  transition: 'transform 0.2s ease',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                More
                <ArrowRight size={20} />
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
