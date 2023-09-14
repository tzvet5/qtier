#pragma once
#include "./constants.hpp"
#include "QDebug"
#include "QObject"
#include "QSet"
#include "exceptions.hpp"
#include "metadata.hpp"
#include "qtgql/qtgql_export.hpp"

namespace qtgql {
namespace bases {

class QTGQL_EXPORT ObjectTypeABC : public QObject {
  Q_OBJECT

  Q_PROPERTY(const QString &__typeName READ __typename CONSTANT)
public:
  using QObject::QObject;

  [[nodiscard]] inline virtual const QString &__typename() const {
    throw exceptions::NotImplementedError(
        {"Derived classes must override this method."});
  }
};

class NodeInterfaceABC;

class QTGQL_EXPORT NodeInterfaceABC : public ObjectTypeABC {
public:
  using ObjectTypeABC::ObjectTypeABC;

  [[nodiscard]] virtual const std::shared_ptr<scalars::Id> &get_id() const = 0;
};

} // namespace bases
} // namespace qtgql
