import React from 'react';

export default function CreditsDisplay({
  freeCredits,
  totalCredits,
  isSubscriber,
  userPlan,
  creditsLoading,
  onClick,
}) {
  const hasCredits = freeCredits > 0;
  const isClickable = !hasCredits && onClick;

  const handleClick = () => {
    if (isClickable) {
      onClick();
    }
  };

  const displayText = () => {
    if (creditsLoading) return '...';
    if (!hasCredits) return 'Get Credits';
    if (isSubscriber) {
      return `${freeCredits}/${totalCredits} (${userPlan})`;
    }
    return `${freeCredits} ${freeCredits === 1 ? 'Credit' : 'Credits'}`;
  };

  return (
    <div
      onClick={handleClick}
      className={`
        px-3 py-1.5
        rounded-lg
        text-sm font-bold
        text-white
        whitespace-nowrap
        transition-all duration-200
        ${hasCredits
          ? 'bg-fusion-pink-gradient'
          : 'bg-fusion-purple-medium cursor-pointer hover:bg-fusion-purple'
        }
      `}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
    >
      {displayText()}
    </div>
  );
}
