interface ComingSoonPageProps {
  title: string;
}

export default function ComingSoonPage({ title }: ComingSoonPageProps) {
  return (
    <div className="coming-soon">
      <h1>{title}</h1>
      <p>
        This feature is in development. Planned functionality includes AI-powered
        pollution insights and neighbourhood-level air quality analysis.
      </p>
    </div>
  );
}
