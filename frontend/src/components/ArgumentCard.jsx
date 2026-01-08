import React from 'react';
import './ArgumentCard.css';

const ArgumentCard = ({ title, content, type, icon }) => {
    return (
        <div className={`argument-card ${type}`}>
            <div className="card-header">
                <span className="card-icon">{icon}</span>
                <h3>{title}</h3>
            </div>
            <div className="card-content">
                {content ? (
                    <div dangerouslySetInnerHTML={{ __html: content.replace(/\n/g, '<br />') }} />
                ) : (
                    <p className="placeholder-text">Waiting for analysis...</p>
                )}
            </div>
        </div>
    );
};

export default ArgumentCard;
