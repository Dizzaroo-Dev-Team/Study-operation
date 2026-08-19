import React from 'react';
import ISFLayout from './ISFLayout';
import ContentArea from './ContentArea';

const ISFViewer = ({ selectedStudy }) => {
  return (
    <ISFLayout selectedStudy={selectedStudy}>
      <ContentArea selectedStudy={selectedStudy} />
    </ISFLayout>
  );
};

export default ISFViewer;
