import { useEffect, useRef, useState, useCallback } from 'react';
import { Building2, ShoppingCart, Headphones, Stethoscope, Scale, GraduationCap, ChevronLeft, ChevronRight } from 'lucide-react';

const useCases = [
  {
    icon: Building2,
    title: 'Enterprise Operations',
    scenario: 'A financial services firm deploys an internal assistant to help employees with HR policies and expense reporting.',
    problem: 'The assistant confidently cites non-existent reimbursement policies, causing employees to submit invalid claims.',
    solution: 'Quality testing detects hallucination patterns where the LLM fabricates policy details, allowing the team to add explicit boundary instructions.',
    testType: 'Hallucination Detection'
  },
  {
    icon: ShoppingCart,
    title: 'E-commerce Support',
    scenario: 'An online retailer uses a chatbot to handle customer inquiries about orders, returns, and product availability.',
    problem: 'When asked vague questions like "where\'s my stuff?", the bot processes orders without confirming which order the customer means.',
    solution: 'Testing reveals ambiguity handling gaps, prompting updates to require order confirmation before taking action.',
    testType: 'Ambiguity Handling'
  },
  {
    icon: Headphones,
    title: 'Customer Service',
    scenario: 'A SaaS company\'s support bot helps users troubleshoot product issues and manage their accounts.',
    problem: 'Users asking for help with one feature receive unsolicited suggestions about upgrading or using other features they didn\'t ask about.',
    solution: 'Scans identify scope creep issues, leading to tighter instructions about staying focused on the user\'s specific request.',
    testType: 'Scope Creep'
  },
  {
    icon: Stethoscope,
    title: 'Healthcare Information',
    scenario: 'A telehealth platform uses an AI assistant to help patients schedule appointments and understand their care instructions.',
    problem: 'The assistant provides specific medical advice when it should only offer general information and direct to professionals.',
    solution: 'Boundary violation tests catch instances where the bot crosses into medical advice, triggering stricter guardrails.',
    testType: 'Boundary Violations'
  },
  {
    icon: Scale,
    title: 'Legal Services',
    scenario: 'A law firm\'s client portal includes an AI that helps clients understand case timelines and document requirements.',
    problem: 'Despite instructions to maintain a formal tone, the assistant occasionally becomes too casual or uses inappropriate humor.',
    solution: 'Instruction following tests identify tone drift, enabling refinement of persona consistency rules.',
    testType: 'Instruction Following'
  },
  {
    icon: GraduationCap,
    title: 'Education Platform',
    scenario: 'An online learning platform uses an AI tutor to help students with coursework across multiple subjects.',
    problem: 'During long tutoring sessions, the AI forgets earlier context about what the student already knows, repeating explanations.',
    solution: 'Context retention testing reveals memory limitations, leading to improved conversation summarization techniques.',
    testType: 'Context Retention'
  }
];

export default function UseCasesSection() {
  const [isVisible, setIsVisible] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(1);
  const [isTransitioning, setIsTransitioning] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const sectionRef = useRef(null);
  const carouselRef = useRef(null);
  const touchStartX = useRef(null);
  const touchStartY = useRef(null);
  const touchCurrentX = useRef(null);
  const touchCurrentY = useRef(null);
  const totalSlides = useCases.length;
  const slides = [useCases[totalSlides - 1], ...useCases, useCases[0]];

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, []);

  // Auto-scroll carousel
  useEffect(() => {
    if (!isVisible || isPaused) return;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev >= totalSlides + 1 ? 1 : prev + 1));
    }, 4000);

    return () => clearInterval(interval);
  }, [isVisible, isPaused, totalSlides]);

  const goToSlide = useCallback((index) => {
    setCurrentIndex(index + 1);
  }, []);

  const goToPrev = useCallback(() => {
    setCurrentIndex((prev) => (prev <= 0 ? totalSlides : prev - 1));
  }, [totalSlides]);

  const goToNext = useCallback(() => {
    setCurrentIndex((prev) => (prev >= totalSlides + 1 ? 1 : prev + 1));
  }, [totalSlides]);

  const normalizeIndex = useCallback((index) => {
    if (totalSlides === 0) {
      return 0;
    }
    return ((index - 1 + totalSlides) % totalSlides) + 1;
  }, [totalSlides]);

  const handleTransitionEnd = () => {
    if (currentIndex === totalSlides + 1) {
      setIsTransitioning(false);
      setCurrentIndex(1);
    } else if (currentIndex === 0) {
      setIsTransitioning(false);
      setCurrentIndex(totalSlides);
    }
  };

  useEffect(() => {
    if (!isTransitioning) {
      const id = requestAnimationFrame(() => setIsTransitioning(true));
      return () => cancelAnimationFrame(id);
    }
    return undefined;
  }, [isTransitioning]);

  const activeIndex = (currentIndex - 1 + totalSlides) % totalSlides;

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        return;
      }
      setIsTransitioning(false);
      setCurrentIndex((prev) => normalizeIndex(prev));
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleVisibilityChange);
    };
  }, [normalizeIndex]);

  const handleTouchStart = (event) => {
    const touch = event.touches[0];
    touchStartX.current = touch.clientX;
    touchStartY.current = touch.clientY;
    touchCurrentX.current = touch.clientX;
    touchCurrentY.current = touch.clientY;
    setIsPaused(true);
  };

  const handleTouchMove = (event) => {
    const touch = event.touches[0];
    touchCurrentX.current = touch.clientX;
    touchCurrentY.current = touch.clientY;
  };

  const handleTouchEnd = () => {
    if (touchStartX.current === null || touchStartY.current === null) {
      setIsPaused(false);
      return;
    }
    const deltaX = touchCurrentX.current - touchStartX.current;
    const deltaY = touchCurrentY.current - touchStartY.current;
    const isHorizontalSwipe = Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY);

    if (isHorizontalSwipe) {
      if (deltaX > 0) {
        goToPrev();
      } else {
        goToNext();
      }
    }

    touchStartX.current = null;
    touchStartY.current = null;
    touchCurrentX.current = null;
    touchCurrentY.current = null;
    setIsPaused(false);
  };

  return (
    <section
      ref={sectionRef}
      style={{
        padding: 'clamp(3rem, 6vw, 5rem) 0',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
        transition: 'opacity 0.6s ease-out, transform 0.6s ease-out'
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 1rem' }}>
        {/* Section header */}
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <h2 style={{
            fontSize: 'clamp(1.75rem, 4vw, 2.5rem)',
            fontWeight: 'bold',
            color: 'white',
            marginBottom: '1rem'
          }}>
            Real-World Use Cases
          </h2>
          <p style={{
            fontSize: '1.125rem',
            color: 'white',
            maxWidth: '700px',
            margin: '0 auto',
            lineHeight: 1.6
          }}>
            See how businesses across industries catch quality issues before they impact customers.
          </p>
        </div>

        {/* Carousel container */}
        <div
          ref={carouselRef}
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          style={{ position: 'relative' }}
          className="use-cases-carousel"
        >
          {/* Navigation arrows */}
          <button
            onClick={goToPrev}
            style={{
              position: 'absolute',
              left: '-1rem',
              top: '50%',
              transform: 'translateY(-50%)',
              zIndex: 10,
              background: 'rgba(80, 77, 154, 0.8)',
              border: '1px solid rgba(102, 196, 225, 0.3)',
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
            className="use-cases-arrow use-cases-arrow-left"
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(102, 196, 225, 0.3)';
              e.currentTarget.style.borderColor = '#66c4e1';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(80, 77, 154, 0.8)';
              e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.3)';
            }}
          >
            <ChevronLeft size={20} color="#66c4e1" />
          </button>
          <button
            onClick={goToNext}
            style={{
              position: 'absolute',
              right: '-1rem',
              top: '50%',
              transform: 'translateY(-50%)',
              zIndex: 10,
              background: 'rgba(80, 77, 154, 0.8)',
              border: '1px solid rgba(102, 196, 225, 0.3)',
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
            className="use-cases-arrow use-cases-arrow-right"
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(102, 196, 225, 0.3)';
              e.currentTarget.style.borderColor = '#66c4e1';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(80, 77, 154, 0.8)';
              e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.3)';
            }}
          >
            <ChevronRight size={20} color="#66c4e1" />
          </button>

          {/* Cards container */}
          <div style={{
            overflow: 'hidden',
            borderRadius: '1rem'
          }}>
            <div style={{
              display: 'flex',
              transition: isTransitioning ? 'transform 0.5s ease-in-out' : 'none',
              transform: `translateX(-${currentIndex * 100}%)`
            }}
            onTransitionEnd={handleTransitionEnd}
            >
              {slides.map((useCase, index) => {
                const Icon = useCase.icon;
                return (
                  <div
                    key={index}
                    style={{
                      minWidth: '100%',
                      padding: '0 clamp(0.75rem, 4vw, 2rem)',
                      boxSizing: 'border-box'
                    }}
                  >
                    <div
                      style={{
                        background: 'rgba(80, 77, 154, 0.25)',
                        border: '1px solid rgba(102, 196, 225, 0.2)',
                        borderRadius: '1rem',
                        padding: 'clamp(1.25rem, 4vw, 2rem)',
                        backdropFilter: 'blur(10px)',
                        maxWidth: '800px',
                        margin: '0 auto',
                        transition: 'border-color 0.3s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#66c4e1';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = 'rgba(102, 196, 225, 0.2)';
                      }}
                    >
                      {/* Header */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                        <div style={{
                          width: '50px',
                          height: '50px',
                          borderRadius: '0.75rem',
                          background: 'linear-gradient(135deg, rgba(102, 196, 225, 0.2), rgba(243, 143, 149, 0.2))',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0
                        }}>
                          <Icon size={24} color="#66c4e1" />
                        </div>
                        <div>
                          <h3 style={{
                            fontSize: '1.25rem',
                            fontWeight: '600',
                            color: 'white',
                            marginBottom: '0.25rem'
                          }}>
                            {useCase.title}
                          </h3>
                          <span style={{
                            fontSize: '0.875rem',
                            color: '#f38f95',
                            fontWeight: '500'
                          }}>
                            {useCase.testType}
                          </span>
                        </div>
                      </div>

                      {/* Scenario */}
                      <p style={{
                        color: 'rgba(255, 255, 255, 0.9)',
                        fontSize: '1rem',
                        lineHeight: 1.6,
                        marginBottom: '1.5rem'
                      }}>
                        {useCase.scenario}
                      </p>

                      {/* Problem & Solution side by side on larger screens */}
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                        gap: '1rem'
                      }}>
                        {/* Problem */}
                        <div style={{
                          background: 'rgba(243, 143, 149, 0.1)',
                          border: '1px solid rgba(243, 143, 149, 0.2)',
                          borderRadius: '0.75rem',
                          padding: '1rem'
                        }}>
                          <p style={{
                            color: '#f38f95',
                            fontSize: '0.875rem',
                            fontWeight: '600',
                            marginBottom: '0.5rem'
                          }}>
                            The Problem
                          </p>
                          <p style={{
                            color: 'rgba(255, 255, 255, 0.8)',
                            fontSize: '0.9rem',
                            lineHeight: 1.5
                          }}>
                            {useCase.problem}
                          </p>
                        </div>

                        {/* Solution */}
                        <div style={{
                          background: 'rgba(102, 196, 225, 0.1)',
                          border: '1px solid rgba(102, 196, 225, 0.2)',
                          borderRadius: '0.75rem',
                          padding: '1rem'
                        }}>
                          <p style={{
                            color: '#66c4e1',
                            fontSize: '0.875rem',
                            fontWeight: '600',
                            marginBottom: '0.5rem'
                          }}>
                            The Solution
                          </p>
                          <p style={{
                            color: 'rgba(255, 255, 255, 0.8)',
                            fontSize: '0.9rem',
                            lineHeight: 1.5
                          }}>
                            {useCase.solution}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Dot indicators */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '0.5rem',
            marginTop: '1.5rem'
          }}>
            {useCases.map((_, index) => (
              <button
                key={index}
                onClick={() => goToSlide(index)}
                style={{
                  width: activeIndex === index ? '24px' : '8px',
                  height: '8px',
                  borderRadius: '4px',
                  background: activeIndex === index ? '#66c4e1' : 'rgba(102, 196, 225, 0.3)',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  padding: 0
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
