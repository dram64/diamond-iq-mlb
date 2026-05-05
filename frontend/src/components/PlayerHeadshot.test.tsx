import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlayerHeadshot, initialsOf } from './PlayerHeadshot';

describe('initialsOf', () => {
  it('returns first+last initials for two-name players', () => {
    expect(initialsOf('Aaron Judge')).toBe('AJ');
    expect(initialsOf('Yordan Alvarez')).toBe('YA');
  });

  it('returns single initial for one-name players', () => {
    expect(initialsOf('Pedro')).toBe('P');
  });

  it('uses first + last token for multi-word names (skipping middles)', () => {
    expect(initialsOf('Fernando Tatis Jr.')).toBe('FT');
    expect(initialsOf('Robinson Cano III')).toBe('RC');
    expect(initialsOf('Ronald Acuña Jr.')).toBe('RA');
  });

  it('returns empty string for missing or blank names', () => {
    expect(initialsOf(null)).toBe('');
    expect(initialsOf(undefined)).toBe('');
    expect(initialsOf('')).toBe('');
    expect(initialsOf('   ')).toBe('');
  });

  it('uppercases lowercase input', () => {
    expect(initialsOf('aaron judge')).toBe('AJ');
  });
});

describe('PlayerHeadshot', () => {
  it('renders an <img> with the MLB CDN URL when playerId is present', () => {
    render(<PlayerHeadshot playerId={592450} playerName="Aaron Judge" />);
    const img = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    expect(img.tagName).toBe('IMG');
    expect(img.src).toContain('img.mlbstatic.com');
    expect(img.src).toContain('/v1/people/592450/headshot/67/current');
  });

  it('sets loading="lazy" and decoding="async" on the image', () => {
    render(<PlayerHeadshot playerId={592450} playerName="Aaron Judge" />);
    const img = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    expect(img.getAttribute('loading')).toBe('lazy');
    expect(img.getAttribute('decoding')).toBe('async');
  });

  it('renders the initials fallback when playerId is null/undefined/empty', () => {
    const { rerender, container } = render(
      <PlayerHeadshot playerId={null} playerName="Aaron Judge" />,
    );
    expect(screen.getByLabelText('Aaron Judge').textContent).toBe('AJ');
    // No <img> element rendered — only the role="img" span fallback.
    expect(container.querySelector('img')).toBeNull();

    rerender(<PlayerHeadshot playerId={undefined} playerName="Yordan Alvarez" />);
    expect(screen.getByLabelText('Yordan Alvarez').textContent).toBe('YA');

    rerender(<PlayerHeadshot playerId="" playerName="Mike Trout" />);
    expect(screen.getByLabelText('Mike Trout').textContent).toBe('MT');
  });

  it('falls back to initials when the image errors', () => {
    render(<PlayerHeadshot playerId={99999999} playerName="Aaron Judge" />);
    const img = screen.getByAltText('Aaron Judge') as HTMLImageElement;
    fireEvent.error(img);
    // After error the <img> is replaced with the initials span.
    expect(screen.queryByAltText('Aaron Judge')).toBeNull();
    expect(screen.getByLabelText('Aaron Judge').textContent).toBe('AJ');
  });

  it('alt text matches playerName', () => {
    render(<PlayerHeadshot playerId={1} playerName="Test Player" />);
    expect(screen.getByAltText('Test Player')).toBeInTheDocument();
  });

  it('renders a blank fallback when both name and id are missing', () => {
    render(<PlayerHeadshot playerId={null} playerName={null} />);
    const span = screen.getByLabelText('Unknown player');
    expect(span.textContent).toBe('');
  });

  it('size prop changes the rendered tailwind classes', () => {
    const { container, rerender } = render(
      <PlayerHeadshot playerId={1} playerName="A B" size="sm" />,
    );
    const img = container.querySelector('img');
    expect(img?.className).toContain('w-8');
    rerender(<PlayerHeadshot playerId={1} playerName="A B" size="lg" />);
    const img2 = container.querySelector('img');
    expect(img2?.className).toContain('w-24');
  });
});
