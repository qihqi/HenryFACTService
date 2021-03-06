import React from 'react';
import styles from './styles';

export default class SkyLightStateless extends React.Component {

  onOverlayClicked() {
    if (this.props.onOverlayClicked) {
      this.props.onOverlayClicked();
    }
  }

  onCloseClicked() {
    if (this.props.onCloseClicked) {
      this.props.onCloseClicked();
    }
  }

  render() {
    const mergeStyles = key => Object.assign({}, styles[key], this.props[key]);
    const { isVisible } = this.props;
    const dialogStyles = mergeStyles('dialogStyles');
    const overlayStyles = mergeStyles('overlayStyles');
    const closeButtonStyle = mergeStyles('closeButtonStyle');
    const titleStyle = mergeStyles('titleStyle');
    overlayStyles.display = dialogStyles.display = 'block';

    let overlay;
    if (this.props.showOverlay) {
      overlay = (
        <div className="skylight-overlay"
          onClick={() => this.onOverlayClicked()}
          style={overlayStyles}
        />
      );
    }
    console.log(isVisible);
    let style = {};
    if (!isVisible) {
        style = {display: 'none'};
    }
    return (
        <section className="skylight-wrapper" style={style}>
            {overlay}
            <div className="skylight-dialog" style={dialogStyles}>
              <a role="button" className="skylight-close-button"
                onClick={() => this.onCloseClicked()}
                style={closeButtonStyle}
              >
                &times;
               </a>
              <h2 style={titleStyle}>{this.props.title}</h2>
              {this.props.children}
            </div>
        </section>
    );
  }
}

SkyLightStateless.displayName = 'SkyLightStateless';

SkyLightStateless.sharedPropTypes = {
  closeButtonStyle: React.PropTypes.object,
  dialogStyles: React.PropTypes.object,
  onCloseClicked: React.PropTypes.func,
  onOverlayClicked: React.PropTypes.func,
  overlayStyles: React.PropTypes.object,
  showOverlay: React.PropTypes.bool,
  title: React.PropTypes.string,
  titleStyle: React.PropTypes.object,
};

SkyLightStateless.propTypes = Object.assign({}, SkyLightStateless.sharedPropTypes);
Object.assign(SkyLightStateless.propTypes, {
  isVisible: React.PropTypes.bool,
});

SkyLightStateless.defaultProps = {
  title: '',
  showOverlay: true,
  overlayStyles: styles.overlayStyles,
  dialogStyles: styles.dialogStyles,
  closeButtonStyle: styles.closeButtonStyle,
};
