import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../../src/components/StatusBadge';

describe('StatusBadge', () => {
  it('renders healthy status correctly', () => {
    render(<StatusBadge status="healthy" />);
    
    const badge = screen.getByText('HEALTHY');
    expect(badge).toBeInTheDocument();
    // The background/dark-text classes live on the outer badge span; the inner
    // text span (returned by getByText) only carries the lighter text color.
    expect(badge.parentElement).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('renders error status correctly', () => {
    render(<StatusBadge status="error" />);
    
    const badge = screen.getByText('ERROR');
    expect(badge).toBeInTheDocument();
    expect(badge.parentElement).toHaveClass('bg-red-100', 'text-red-800');
  });

  it('renders warning status correctly', () => {
    render(<StatusBadge status="warning" />);
    
    const badge = screen.getByText('WARNING');
    expect(badge).toBeInTheDocument();
    expect(badge.parentElement).toHaveClass('bg-yellow-100', 'text-yellow-800');
  });

  it('hides icon when showIcon is false', () => {
    render(<StatusBadge status="healthy" showIcon={false} />);
    
    const badge = screen.getByText('HEALTHY');
    const icon = badge.previousElementSibling;
    expect(icon).not.toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(<StatusBadge status="healthy" className="custom-class" />);
    
    const badge = screen.getByText('HEALTHY').parentElement;
    expect(badge).toHaveClass('custom-class');
  });
});
